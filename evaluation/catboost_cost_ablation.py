"""Compare cost losses on stored attempts; no LLM requests or new labels."""
import json

import numpy as np
from catboost import CatBoostRegressor
from scipy.stats import spearmanr
from sklearn.metrics import mean_absolute_error
from sklearn.model_selection import GroupKFold

from evaluation.quality_dataset import ROOT
from evaluation.compare_all_predictors import policy_cohort, replay
from evaluation.train_catboost_large import REPORT, load_training_rows
from runtime.predictor import features
from runtime.tasks import load_task

VARIANTS = {'rmse': ('RMSE', False), 'mae': ('MAE', False),
            'huber_200': ('Huber:delta=200', False), 'log_rmse': ('RMSE', True)}
EXPORTED = {'mae': 'catboost_large_mae', 'huber_200': 'catboost_large_huber'}


def fit(name, x, cost):
    loss, logarithm = VARIANTS[name]
    target = np.log1p(cost) if logarithm else cost
    model = CatBoostRegressor(depth=3, iterations=150, l2_leaf_reg=10,
                              random_seed=71, verbose=False, thread_count=2,
                              allow_writing_files=False, loss_function=loss)
    model.fit(x, target)
    return model


def predict(model, name, x):
    raw = model.predict(x)
    return np.maximum(50, np.expm1(raw) if VARIANTS[name][1] else raw)


def metrics(actual, predicted):
    error = abs(actual-predicted)
    return dict(mae=float(error.mean()), median_ae=float(np.median(error)),
                p90_ae=float(np.quantile(error,.9)),
                spearman=float(spearmanr(actual,predicted).statistic),
                severe_underestimate=float(np.mean(predicted*2<actual)))


def main():
    rows, quality, labels, held_groups = load_training_rows()
    x = np.asarray([features(r['task'], keywords=False) for r in rows], dtype=np.float32)
    cost = np.asarray([r['cost'] for r in rows])
    groups = [r['group'] for r in rows]
    assert not set(groups) & held_groups
    folds = list(GroupKFold(n_splits=5).split(x, cost, groups))
    holdout = [r for r in quality if r['split']=='holdout']
    hx = np.asarray([features(load_task(ROOT/'benchmarks'/(r['source']+'-v1')/'input'/r['source_id']),
                              keywords=False) for r in holdout],dtype=np.float32)
    hc = np.asarray([labels[r['id']]['cost'] for r in holdout])
    cohort = policy_cohort()
    cx = np.asarray([features(task, keywords=False) for task, _ in cohort], dtype=np.float32)
    cc = np.asarray([row['cost'] for _, row in cohort])
    results = {}
    for name in VARIANTS:
        oof = np.zeros(len(rows))
        for train, test in folds:
            model = fit(name, x[train], cost[train])
            oof[test] = predict(model, name, x[test])
        full = fit(name, x, cost)
        if name in EXPORTED:
            full.save_model(str(ROOT / 'predictors' / (EXPORTED[name] + '_cost.cbm')))
        cohort_prediction = predict(full, name, cx)
        ordering = {task.id: (.5, float(predicted))
                    for (task, _), predicted in zip(cohort, cohort_prediction)}
        results[name] = dict(group_cv=metrics(cost,oof),
                             holdout_diagnostic=metrics(hc,predict(full,name,hx)),
                             selected_cohort_diagnostic=metrics(cc,cohort_prediction),
                             selected_cohort_replay_25k=replay(cohort, ordering, 25000,
                                                               use_success=False))
        print(name,json.dumps(results[name]),flush=True)
    chosen = min(results, key=lambda n: (results[n]['group_cv']['mae'],
                                         -results[n]['group_cv']['spearman']))
    report = dict(rows=len(rows), groups=len(set(groups)), variants=results,
                  selected_by_group_cv_mae=chosen,
                  note='All labels are stored real agent attempts. The 44-task holdout has been '
                       'inspected in previous experiments and is only diagnostic. The 98-task '
                       'cohort is selected by an older CatBoost queue and is also diagnostic. '
                       'No model is deployed by this script; proxy billing may differ from local weighted tokens.')
    (REPORT/'catboost-cost-ablation.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
    print('SELECTED',chosen,flush=True)


if __name__=='__main__':
    main()
