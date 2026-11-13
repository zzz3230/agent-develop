"""Tiny perceptron cost predictors on the same stored, group-separated labels."""
import json
import warnings

import numpy as np
from sklearn.exceptions import ConvergenceWarning
from sklearn.model_selection import GroupKFold
from sklearn.neural_network import MLPRegressor
from sklearn.preprocessing import StandardScaler

from evaluation.quality_dataset import ROOT
from evaluation.train_catboost_large import REPORT, load_training_rows
from evaluation.catboost_cost_ablation import metrics
from runtime.predictor import features
from runtime.tasks import load_task

CONFIGS = {'mlp_16': (16,), 'mlp_32_16': (32, 16)}


def fit_predict(shape, train_x, train_y, test_x):
    scaler = StandardScaler().fit(train_x)
    mean, scale = float(train_y.mean()), float(train_y.std()) or 1.0
    with warnings.catch_warnings():
        warnings.simplefilter('ignore', ConvergenceWarning)
        model = MLPRegressor(hidden_layer_sizes=shape, solver='lbfgs', alpha=10.0,
                             max_iter=350, random_state=71).fit(
                                 scaler.transform(train_x), (train_y - mean) / scale)
    return np.maximum(50.0, model.predict(scaler.transform(test_x)) * scale + mean)


def main():
    rows, quality, labels, held_groups = load_training_rows()
    x = np.asarray([features(r['task'], keywords=False) for r in rows], dtype=np.float32)
    cost = np.asarray([r['cost'] for r in rows])
    groups = [r['group'] for r in rows]
    assert not set(groups) & held_groups
    folds = list(GroupKFold(n_splits=5).split(x, cost, groups))
    held = [r for r in quality if r['split'] == 'holdout']
    hx = np.asarray([features(load_task(ROOT / 'benchmarks' / (r['source'] + '-v1') /
                                       'input' / r['source_id']), keywords=False) for r in held], dtype=np.float32)
    hc = np.asarray([labels[r['id']]['cost'] for r in held])
    results = {}
    for name, shape in CONFIGS.items():
        oof = np.zeros(len(rows))
        for train, test in folds:
            oof[test] = fit_predict(shape, x[train], cost[train], x[test])
        results[name] = dict(group_cv=metrics(cost, oof),
                             holdout_diagnostic=metrics(hc, fit_predict(shape, x, cost, hx)))
        print(name, json.dumps(results[name]), flush=True)
    report = dict(rows=len(rows), groups=len(set(groups)), variants=results,
                  note='Offline only. Held-out 44 tasks were previously inspected; no neural model deployed.')
    (REPORT / 'mlp-cost-ablation.json').write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')


if __name__ == '__main__':
    main()
