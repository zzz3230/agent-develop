"""Larger retrospective CatBoost check on attempted tasks in four saved pool200 runs."""
import json
import argparse
from pathlib import Path

import numpy as np
from catboost import CatBoostClassifier, CatBoostRegressor
from sklearn.metrics import brier_score_loss, mean_absolute_error, roc_auc_score

from evaluation.quality_dataset import META, ROOT
from runtime.predictor import Predictor, features
from runtime.tasks import load_task

REPORT = ROOT / 'docs/results/quality-minilm-v1'
POOL = ROOT / 'benchmark-runs/planner-200-eval-101-v2/input'


def main():
    cli = argparse.ArgumentParser()
    cli.add_argument('--reports-dir', type=Path)
    source = cli.parse_args().reports_dir
    manifest = json.loads((META / 'manifest.json').read_text(encoding='utf-8'))['tasks']
    labels = {r['id']: r for path in (REPORT / 'cached-labels.json', REPORT / 'new-labels.json')
              for r in json.loads(path.read_text(encoding='utf-8'))}
    training = [r for r in manifest if r['split'] == 'train']
    x = np.asarray([features(load_task(ROOT / 'benchmarks' / (r['source'] + '-v1') / 'input' / r['source_id']), False)
                    for r in training], dtype=np.float32)
    y = np.array([labels[r['id']]['correct'] for r in training])
    cost = np.array([labels[r['id']]['cost'] for r in training])
    config = {'depth': 3, 'iterations': 150, 'l2_leaf_reg': 10, 'random_seed': 71,
              'verbose': False, 'thread_count': 2, 'allow_writing_files': False}
    classifier = CatBoostClassifier(**config, loss_function='Logloss').fit(x, y)
    regressor = CatBoostRegressor(**config, loss_function='RMSE').fit(x, cost)

    observed = {}
    if source:
        files = [source / f'{name}-pool200-50k.json' for name in ('base', 'r3', 'r4', 'r5')]
    else:
        files = sorted((ROOT / 'benchmark-runs/pool200-budget50000').glob('*/graded.json'))
    for path in files:
        report = json.loads(path.read_text(encoding='utf-8'))
        for row in report['rows']:
            if row.get('cost') and row['cost'] > 0:
                observed.setdefault(row['id'], []).append(row)
    paths = {p.name.split('_', 1)[1]: p for p in POOL.iterdir() if p.is_dir()}
    ids = sorted(observed)
    assert len(ids) > 44 and all(i in paths for i in ids)
    tasks = [load_task(paths[i]) for i in ids]
    numeric = np.asarray([features(t, False) for t in tasks], dtype=np.float32)
    predictions = {'catboost_structural': (classifier.predict_proba(numeric)[:, 1], regressor.predict(numeric))}
    for mode in ('quality_minilm_structural', 'embedding'):
        predictor = Predictor(tasks, mode, ROOT / 'predictors')
        predictions[mode] = tuple(np.array([predictor.predictions[t.id][j] for t in tasks]) for j in (0, 1))
    # Multiple attempts are stochastic; compare predictions to the per-task mean outcome and price.
    actual_p = np.array([np.mean([r['correct'] for r in observed[i]]) for i in ids])
    actual_cost = np.array([np.mean([r['cost'] for r in observed[i]]) for i in ids])
    result = {'unique_tasks': len(ids), 'attempts': sum(map(len, observed.values())),
              'source_runs': [p.parent.name if not source else p.stem for p in files], 'models': {}}
    for mode, (p, c) in predictions.items():
        result['models'][mode] = {'mean_outcome_brier': float(np.mean((p - actual_p) ** 2)),
                                  'cost_mae': float(mean_absolute_error(actual_cost, c)),
                                  'p_min': float(p.min()), 'p_max': float(p.max()),
                                  'p_std': float(p.std())}
    result['constant_training_mean_brier'] = float(np.mean((y.mean() - actual_p) ** 2))
    result['constant_training_mean_cost_mae'] = float(np.mean(abs(cost.mean() - actual_cost)))
    (REPORT / ('catboost-pool200-main.json' if source else 'catboost-pool200-local.json')).write_text(
        json.dumps(result, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(result, indent=2), flush=True)


if __name__ == '__main__':
    main()
