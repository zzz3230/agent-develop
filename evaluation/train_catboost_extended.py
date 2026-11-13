"""Train bounded structural-feature CatBoost heads from stored attempt labels."""
import json

import numpy as np
from catboost import CatBoostClassifier, CatBoostRegressor
from scipy.stats import spearmanr
from sklearn.metrics import brier_score_loss
from sklearn.model_selection import GroupKFold

from evaluation.catboost_cost_ablation import metrics
from evaluation.compare_all_predictors import policy_cohort, replay
from evaluation.quality_dataset import ROOT
from evaluation.train_catboost_large import REPORT, load_training_rows
from runtime.predictor import features
from runtime.tasks import load_task

LOSSES = {'MAE': 'MAE', 'Huber': 'Huber:delta=200', 'RMSE': 'RMSE'}
COMMON = dict(depth=3, iterations=150, l2_leaf_reg=10, random_seed=71,
              verbose=False, thread_count=2, allow_writing_files=False)


def classifier(x, y):
    return CatBoostClassifier(**COMMON, loss_function='Logloss').fit(x, y)


def regressor(loss, x, cost):
    return CatBoostRegressor(**COMMON, loss_function=LOSSES[loss]).fit(x, cost)


def main():
    rows, quality, labels, held_groups = load_training_rows()
    x = np.asarray([features(r['task'], keywords=False, extended=True) for r in rows], dtype=np.float32)
    y = np.asarray([r['correct'] for r in rows])
    cost = np.asarray([r['cost'] for r in rows])
    groups = [r['group'] for r in rows]
    assert x.shape == (301, 29) and not set(groups) & held_groups
    folds = list(GroupKFold(n_splits=5).split(x, y, groups))
    probabilities = np.zeros(len(rows))
    for train, test in folds:
        probabilities[test] = classifier(x[train], y[train]).predict_proba(x[test])[:,1]
    results = {}
    holdout = [r for r in quality if r['split'] == 'holdout']
    hx = np.asarray([features(load_task(ROOT/'benchmarks'/(r['source']+'-v1')/'input'/r['source_id']),
                              keywords=False, extended=True) for r in holdout], dtype=np.float32)
    hc = np.asarray([labels[r['id']]['cost'] for r in holdout])
    hy = np.asarray([labels[r['id']]['correct'] for r in holdout])
    cohort = policy_cohort()
    cx = np.asarray([features(task, keywords=False, extended=True) for task,_ in cohort],dtype=np.float32)
    cc = np.asarray([r['cost'] for _,r in cohort])
    for name in LOSSES:
        predicted = np.zeros(len(rows))
        for train, test in folds:
            predicted[test] = np.maximum(50,regressor(name,x[train],cost[train]).predict(x[test]))
        full = regressor(name,x,cost)
        cp = np.maximum(50,full.predict(cx))
        ordering = {task.id:(.5,float(c)) for (task,_),c in zip(cohort,cp)}
        results[name] = dict(group_cv=metrics(cost,predicted),
                             holdout_diagnostic=metrics(hc,np.maximum(50,full.predict(hx))),
                             selected_cohort_diagnostic=metrics(cc,cp),
                             selected_cohort_replay_25k=replay(cohort,ordering,25000,use_success=False))
        print(name,json.dumps(results[name]),flush=True)
    selected = min(results,key=lambda n:(results[n]['group_cv']['mae'],
                                         -results[n]['group_cv']['spearman']))
    success_model = classifier(x,y)
    cost_model = regressor(selected,x,cost)
    success_model.save_model(str(ROOT/'predictors/catboost_extended_success.cbm'))
    cost_model.save_model(str(ROOT/'predictors/catboost_extended_cost.cbm'))
    report = dict(rows=len(rows),groups=len(set(groups)),features=int(x.shape[1]),
                  selected_loss=selected,group_cv_brier=float(brier_score_loss(y,probabilities)),
                  holdout_brier=float(brier_score_loss(hy,success_model.predict_proba(hx)[:,1])),
                  results=results,
                  note='Selection uses grouped CV only. Holdout and 98-task cohort are previously inspected '
                       'diagnostics. Training uses stored attempts, with no LLM calls. Proxy billing may differ.')
    (REPORT/'catboost-extended-training.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
    print('SELECTED',selected,'Brier',report['group_cv_brier'],flush=True)


if __name__=='__main__':
    main()
