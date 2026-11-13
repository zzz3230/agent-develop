"""Fit CatBoost on measured quality cases plus 213 new family-safe planner instances."""
import hashlib
import json

import numpy as np
from catboost import CatBoostClassifier, CatBoostRegressor
from sklearn.metrics import brier_score_loss, mean_absolute_error
from sklearn.model_selection import GroupKFold
from scipy.stats import spearmanr

from evaluation.quality_dataset import META, ROOT, input_hash
from runtime.predictor import features
from runtime.tasks import load_task

REPORT = ROOT / 'docs/results/quality-minilm-v1'
NEW = ROOT / 'benchmark-runs/quality-large-v1'
SOURCE = ROOT / 'benchmarks/planner-500/train'
CONFIGS = (dict(depth=2, iterations=100, l2_leaf_reg=10),
           dict(depth=3, iterations=150, l2_leaf_reg=10),
           dict(depth=4, iterations=150, l2_leaf_reg=20))


def models(config, x, success, cost):
    common = dict(**config, random_seed=71, verbose=False, thread_count=2, allow_writing_files=False)
    return (CatBoostClassifier(**common, loss_function='Logloss').fit(x, success),
            CatBoostRegressor(**common, loss_function='RMSE').fit(x, cost))


def main():
    quality = json.loads((META / 'manifest.json').read_text(encoding='utf-8'))['tasks']
    labels = {r['id']: r for path in (REPORT / 'cached-labels.json', REPORT / 'new-labels.json')
              for r in json.loads(path.read_text(encoding='utf-8'))}
    held_groups = {r['group'] for r in quality if r['split'] == 'holdout'}
    family_group = {r['family']: r['group'] for r in quality}
    rows = []
    for r in quality:
        if r['split'] != 'train':
            continue
        path = ROOT / 'benchmarks' / (r['source'] + '-v1') / 'input' / r['source_id']
        assert input_hash(path) == r['input_sha256']
        rows.append(dict(source='quality', id=r['id'], group=r['group'], task=load_task(path),
                         correct=labels[r['id']]['correct'], cost=labels[r['id']]['cost']))
    added = json.loads((NEW / 'manifest.json').read_text(encoding='utf-8'))
    assert added['count'] == 213
    source_manifest = {r['id']: r for r in json.loads((SOURCE / 'manifest.json').read_text(encoding='utf-8'))['tasks']}
    for batch in added['batches']:
        report_path = NEW / batch['name'] / 'run/graded.json'
        report = json.loads(report_path.read_text(encoding='utf-8'))
        actual = {r['id']: r for r in report['rows']}
        assert set(actual) == set(batch['ids'])
        if report['stop'] != 'all tasks handled':
            retry = json.loads((NEW / batch['name'] / 'retry-run/graded.json').read_text(encoding='utf-8'))
            assert retry['stop'] == 'all tasks handled'
            for entry in retry['rows']:
                assert actual[entry['id']]['cost'] <= 0 and entry['cost'] > 0
                actual[entry['id']] = entry
        for identifier in batch['ids']:
            source_row = source_manifest[identifier]
            group = family_group.get(source_row['family'], source_row['family'])
            assert group not in held_groups
            entry = actual[identifier]
            assert entry['cost'] and entry['cost'] > 0
            rows.append(dict(source='planner_train', id=identifier, group=group,
                             task=load_task(SOURCE / 'input' / identifier),
                             correct=int(entry['correct']), cost=entry['cost']))
    assert len(rows) == 301
    x = np.asarray([features(r['task'], keywords=False) for r in rows], dtype=np.float32)
    y = np.asarray([r['correct'] for r in rows])
    cost = np.asarray([r['cost'] for r in rows])
    groups = [r['group'] for r in rows]
    assert len(set(groups)) >= 90 and not set(groups) & held_groups
    folds = list(GroupKFold(n_splits=5).split(x, y, groups))
    candidates = []
    for config in CONFIGS:
        p = np.zeros(len(rows)); c = np.zeros(len(rows))
        for a, b in folds:
            classifier, regressor = models(config, x[a], y[a], cost[a])
            p[b] = classifier.predict_proba(x[b])[:, 1]
            c[b] = regressor.predict(x[b])
        candidates.append(dict(config=config, brier=float(brier_score_loss(y, p)),
                               cost_mae=float(mean_absolute_error(cost, c)),
                               cost_spearman=float(spearmanr(cost, c).statistic)))
    selected = min(candidates, key=lambda r: r['brier'] + r['cost_mae']/5000)
    classifier, regressor = models(selected['config'], x, y, cost)
    classifier.save_model(str(ROOT / 'predictors/catboost_large_success.cbm'))
    regressor.save_model(str(ROOT / 'predictors/catboost_large_cost.cbm'))
    holdout = [r for r in quality if r['split'] == 'holdout']
    holdout_x = np.asarray([features(load_task(ROOT / 'benchmarks' / (r['source'] + '-v1') /
                                             'input' / r['source_id']), keywords=False) for r in holdout],
                           dtype=np.float32)
    holdout_y = np.asarray([labels[r['id']]['correct'] for r in holdout])
    holdout_cost = np.asarray([labels[r['id']]['cost'] for r in holdout])
    def evaluate(clf, reg):
        hp = clf.predict_proba(holdout_x)[:, 1]
        hc = reg.predict(holdout_x)
        return dict(brier=float(brier_score_loss(holdout_y, hp)),
                    cost_mae=float(mean_absolute_error(holdout_cost, hc)),
                    cost_spearman=float(spearmanr(holdout_cost, hc).statistic))
    old_classifier = CatBoostClassifier()
    old_classifier.load_model(str(ROOT / 'predictors/catboost_structural_success.cbm'))
    old_regressor = CatBoostRegressor()
    old_regressor.load_model(str(ROOT / 'predictors/catboost_structural_cost.cbm'))
    report = dict(rows=len(rows), groups=len(set(groups)), successes=int(y.sum()),
                  sources={'quality': 88, 'planner_train': 213}, candidates=candidates, selected=selected,
                  mean_cost=float(cost.mean()), median_cost=float(np.median(cost)),
                  constant_mean_mae=float(mean_absolute_error(cost, np.full(len(cost), cost.mean()))),
                  holdout=dict(rows=len(holdout), large=evaluate(classifier, regressor),
                               old_structural=evaluate(old_classifier, old_regressor)),
                  note='All 213 additional labels are measured agent attempts. Group CV excludes known holdout groups; '
                       'planner instances repeat source families and are not 213 independent algorithms.')
    (REPORT / 'catboost-large-training.json').write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(report), flush=True)


if __name__ == '__main__':
    main()
