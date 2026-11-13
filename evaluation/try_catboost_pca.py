"""Compare small PCA projections of MiniLM for CatBoost without holdout tuning."""
import json

import numpy as np
from catboost import CatBoostClassifier, CatBoostRegressor
from sklearn.decomposition import PCA
from sklearn.metrics import brier_score_loss, mean_absolute_error
from sklearn.model_selection import GroupKFold

from evaluation.quality_dataset import META, ROOT, input_hash
from evaluation.predictor_data import embedded
from runtime.predictor import features
from runtime.tasks import load_task

REPORT = ROOT / 'docs/results/quality-minilm-v1'
CONFIG = dict(depth=3, iterations=150, l2_leaf_reg=10, random_seed=71,
              verbose=False, thread_count=2, allow_writing_files=False)


def fit_models(x, y, cost):
    clf = CatBoostClassifier(**CONFIG, loss_function='Logloss').fit(x, y)
    reg = CatBoostRegressor(**CONFIG, loss_function='RMSE').fit(x, cost)
    return clf, reg


def main():
    manifest = json.loads((META / 'manifest.json').read_text(encoding='utf-8'))['tasks']
    labels = {r['id']: r for path in (REPORT / 'cached-labels.json', REPORT / 'new-labels.json')
              for r in json.loads(path.read_text(encoding='utf-8'))}
    parts = {'train': [], 'holdout': []}
    for row in manifest:
        path = ROOT / 'benchmarks' / (row['source'] + '-v1') / 'input' / row['source_id']
        assert input_hash(path) == row['input_sha256']
        parts[row['split']].append((row, load_task(path)))
    assert len(parts['train']) == 88 and len(parts['holdout']) == 44
    assert {r['group'] for r, _ in parts['train']}.isdisjoint({r['group'] for r, _ in parts['holdout']})
    numeric = {part: np.asarray([features(t, False) for _, t in rows], dtype=np.float32)
               for part, rows in parts.items()}
    vectors = {part: embedded([{'task': t} for _, t in rows], False) for part, rows in parts.items()}
    y = {part: np.array([labels[r['id']]['correct'] for r, _ in rows]) for part, rows in parts.items()}
    cost = {part: np.array([labels[r['id']]['cost'] for r, _ in rows]) for part, rows in parts.items()}
    groups = [r['group'] for r, _ in parts['train']]
    folds = list(GroupKFold(n_splits=5).split(numeric['train'], y['train'], groups))
    candidates = []
    for size in (0, 8, 16, 32):
        prob = np.zeros(len(y['train']))
        price = np.zeros(len(y['train']))
        for a, b in folds:
            xa, xb = numeric['train'][a], numeric['train'][b]
            if size:
                pca = PCA(n_components=size, random_state=71).fit(vectors['train'][a])
                xa = np.hstack([xa, pca.transform(vectors['train'][a])]).astype(np.float32)
                xb = np.hstack([xb, pca.transform(vectors['train'][b])]).astype(np.float32)
            clf, reg = fit_models(xa, y['train'][a], cost['train'][a])
            prob[b] = clf.predict_proba(xb)[:, 1]
            price[b] = reg.predict(xb)
        row = dict(pca_components=size, oof_brier=float(brier_score_loss(y['train'], prob)),
                   oof_cost_mae=float(mean_absolute_error(cost['train'], price)))
        candidates.append(row)
        print('CV', json.dumps(row), flush=True)
    # Success quality is the primary selection metric. Size zero is the no-encoder control.
    selected = min(candidates, key=lambda row: (row['oof_brier'], row['pca_components']))
    diagnostic = []
    for item in candidates:
        size = item['pca_components']
        xa, xb = numeric['train'], numeric['holdout']
        if size:
            pca = PCA(n_components=size, random_state=71).fit(vectors['train'])
            xa = np.hstack([xa, pca.transform(vectors['train'])]).astype(np.float32)
            xb = np.hstack([xb, pca.transform(vectors['holdout'])]).astype(np.float32)
        clf, reg = fit_models(xa, y['train'], cost['train'])
        p = clf.predict_proba(xb)[:, 1]
        c = reg.predict(xb)
        diagnostic.append(dict(pca_components=size, brier=float(brier_score_loss(y['holdout'], p)),
                               cost_mae=float(mean_absolute_error(cost['holdout'], c)),
                               p_min=float(p.min()), p_max=float(p.max()), p_std=float(p.std())))
    result = dict(training_rows=88, holdout_rows=44, candidates=candidates, selected=selected,
                  holdout_diagnostic=diagnostic,
                  note='PCA fitted inside each training fold; size selected by training OOF Brier only. '
                       'Holdout diagnostics for all sizes are exploratory and not used for model selection. '
                       'Zero components is the no-encoder control.')
    path = REPORT / 'catboost-pca.json'
    path.write_text(json.dumps(result, indent=2) + '\n', encoding='utf-8')
    print('RESULT', json.dumps(result), flush=True)


if __name__ == '__main__':
    main()
