"""Offline CatBoost trial on the frozen 88/44 quality split; no agent API calls."""
import json
from pathlib import Path

import numpy as np
from catboost import CatBoostClassifier, CatBoostRegressor
from sklearn.metrics import brier_score_loss, mean_absolute_error
from sklearn.model_selection import GroupKFold

from evaluation.quality_dataset import META, ROOT, input_hash
from evaluation.predictor_data import embedded
from runtime.predictor import features
from runtime.tasks import load_task

REPORT = ROOT / 'docs/results/quality-minilm-v1'


def main():
    manifest = json.loads((META / 'manifest.json').read_text(encoding='utf-8'))['tasks']
    labels = {r['id']: r for path in (REPORT / 'cached-labels.json', REPORT / 'new-labels.json')
              for r in json.loads(path.read_text(encoding='utf-8'))}
    parts = {'train': [], 'holdout': []}
    for row in manifest:
        task_dir = ROOT / 'benchmarks' / (row['source'] + '-v1') / 'input' / row['source_id']
        assert input_hash(task_dir) == row['input_sha256']
        parts[row['split']].append((row, load_task(task_dir)))
    assert len(parts['train']) == 88 and len(parts['holdout']) == 44
    assert {r['group'] for r, _ in parts['train']}.isdisjoint({r['group'] for r, _ in parts['holdout']})
    y = {part: np.array([labels[r['id']]['correct'] for r, _ in rows]) for part, rows in parts.items()}
    cost = {part: np.array([labels[r['id']]['cost'] for r, _ in rows]) for part, rows in parts.items()}
    groups = [r['group'] for r, _ in parts['train']]
    configs = [{'depth': 2, 'iterations': 100, 'l2_leaf_reg': 10},
               {'depth': 3, 'iterations': 150, 'l2_leaf_reg': 10},
               {'depth': 4, 'iterations': 150, 'l2_leaf_reg': 20}]
    results = {}
    for name, keywords, use_embedding in [('structural', False, False), ('keywords', True, False),
                                          ('structural_minilm', False, True)]:
        x = {part: np.asarray([features(t, keywords=keywords) for _, t in rows], dtype=np.float32)
             for part, rows in parts.items()}
        if use_embedding:
            for part, rows in parts.items():
                x[part] = np.hstack([x[part], embedded([{'task': t} for _, t in rows], False)]).astype(np.float32)
        folds = list(GroupKFold(n_splits=5).split(x['train'], y['train'], groups))
        scores = []
        for config in configs:
            prob = np.zeros(len(y['train']))
            predicted_cost = np.zeros(len(y['train']))
            for a, b in folds:
                common = dict(**config, loss_function='Logloss', random_seed=71, verbose=False, thread_count=2,
                              allow_writing_files=False)
                clf = CatBoostClassifier(**common).fit(x['train'][a], y['train'][a])
                reg = CatBoostRegressor(**{**common, 'loss_function': 'RMSE'}).fit(x['train'][a], cost['train'][a])
                prob[b] = clf.predict_proba(x['train'][b])[:, 1]
                predicted_cost[b] = reg.predict(x['train'][b])
            scores.append({'config': config, 'oof_brier': float(brier_score_loss(y['train'], prob)),
                           'oof_cost_mae': float(mean_absolute_error(cost['train'], predicted_cost))})
        selected = min(scores, key=lambda s: s['oof_brier'] + s['oof_cost_mae'] / 5000)
        config = selected['config']
        common = dict(**config, loss_function='Logloss', random_seed=71, verbose=False, thread_count=2,
                      allow_writing_files=False)
        clf = CatBoostClassifier(**common).fit(x['train'], y['train'])
        reg = CatBoostRegressor(**{**common, 'loss_function': 'RMSE'}).fit(x['train'], cost['train'])
        if name == 'structural':
            clf.save_model(str(ROOT / 'predictors/catboost_structural_success.cbm'))
            reg.save_model(str(ROOT / 'predictors/catboost_structural_cost.cbm'))
        p = clf.predict_proba(x['holdout'])[:, 1]
        c = reg.predict(x['holdout'])
        results[name] = {'candidates': scores, 'selected': selected,
                         'holdout_brier': float(brier_score_loss(y['holdout'], p)),
                         'holdout_cost_mae': float(mean_absolute_error(cost['holdout'], c)),
                         'holdout_p_min': float(p.min()), 'holdout_p_max': float(p.max()),
                         'holdout_p_std': float(p.std()), 'feature_count': int(x['train'].shape[1])}
        print(name, json.dumps(results[name]), flush=True)
    dest = REPORT / 'catboost-trial.json'
    dest.write_text(json.dumps({'training_rows': 88, 'holdout_rows': 44, 'results': results}, indent=2) + '\n', encoding='utf-8')
    print(dest, flush=True)


if __name__ == '__main__':
    main()
