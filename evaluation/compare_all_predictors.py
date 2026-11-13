"""Compare every selectable predictor on the same frozen, measured attempts.

This is a retrospective replay, not a new agent run. The second cohort consists
only of tasks attempted by the CatBoost cost-only trial and is selection-biased.
"""
import json
import os
import time
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import numpy as np
from scipy.stats import spearmanr

from evaluation.quality_dataset import META, ROOT
from runtime.predictor import Predictor
from runtime.task_queue import TaskQueue
from runtime.tasks import load_task


MODES = ('numeric', 'embedding', 'structural', 'strong_embedding',
         'bge_structural', 'bge_keywords', 'quality_minilm_structural',
         'quality_minilm_keywords', 'catboost_structural', 'catboost_large')
REPORT = ROOT / 'docs/results/quality-minilm-v1'


def quality_holdout():
    manifest = json.loads((META / 'manifest.json').read_text(encoding='utf-8'))['tasks']
    labels = {r['id']: r for file in ('cached-labels.json', 'new-labels.json')
              for r in json.loads((REPORT / file).read_text(encoding='utf-8'))}
    rows = []
    for row in manifest:
        if row['split'] != 'holdout':
            continue
        task = replace(load_task(ROOT / 'benchmarks' / (row['source'] + '-v1') /
                                 'input' / row['source_id']), id=row['id'])
        label = labels[row['id']]
        rows.append((task, dict(id=task.id, type=task.type, reward=task.reward,
                                correct=bool(label['correct']), cost=float(label['cost']),
                                status='solved' if label['correct'] else 'failed')))
    assert len(rows) == 44 and all(r['cost'] > 0 for _, r in rows)
    return rows


def policy_cohort():
    path = ROOT / 'benchmark-runs/catboost-policy-200-50k/cost_only/graded.json'
    report = json.loads(path.read_text(encoding='utf-8'))
    rows = []
    for row in report['rows']:
        if row['cost'] <= 0:
            continue
        task = load_task(ROOT / 'benchmarks/quality-holdout-200/input' / row['id'])
        assert task.id == row['id'] and task.reward == row['reward']
        rows.append((task, dict(id=task.id, type=task.type, reward=task.reward,
                                correct=bool(row['correct']), cost=float(row['cost']),
                                status=row['journal_status'])))
    assert len(rows) == 98
    return rows


def replay(rows, predictions, budget, use_success=True, enabled=True):
    tasks = [t for t, _ in rows]
    by_id = {r['id']: r for _, r in rows}
    with patch.dict(os.environ, {'PREDICTOR': 'baseline', 'QUEUE_USE_SUCCESS': str(int(use_success)),
                                'QUEUE_POLICY': 'greedy', 'CODING_PRECHECK': '0', 'SCORE_ALPHA': '1'}):
        queue = TaskQueue(tasks, enabled=enabled)
        if predictions is not None:
            queue.predictor = SimpleNamespace(predictions=predictions)
        spent = points = 0.0
        correct = completed = 0
        while queue.fresh:
            task, _ = queue.next(max(0, budget - spent))
            row = by_id[task.id]
            if spent + row['cost'] > budget:
                break
            spent += row['cost']
            completed += 1
            if row['correct']:
                points += row['reward']
                correct += 1
            queue.record(task, row['status'], row['cost'])
    return dict(points=points, correct=correct, completed=completed, spent=round(spent, 1))


def evaluate(rows, budget):
    tasks = [t for t, _ in rows]
    labels = [r for _, r in rows]
    costs = np.asarray([r['cost'] for r in labels])
    outcomes = np.asarray([r['correct'] for r in labels], dtype=float)
    result = dict(tasks=len(rows), mean_cost=float(costs.mean()), successes=int(outcomes.sum()),
                  budget=budget, models={})
    result['baseline'] = dict(dynamic_type=replay(rows, None, budget),
                              directory_order=replay(rows, None, budget, enabled=False))
    for mode in MODES:
        start = time.perf_counter()
        predictor = Predictor(tasks, mode, ROOT / 'predictors')
        elapsed = time.perf_counter() - start
        predictions = predictor.predictions
        p = np.asarray([predictions[t.id][0] for t in tasks])
        c = np.asarray([predictions[t.id][1] for t in tasks])
        result['models'][mode] = dict(brier=float(np.mean((p - outcomes)**2)),
                                      cost_mae=float(np.mean(abs(c-costs))),
                                      cost_spearman=float(spearmanr(c, costs).statistic),
                                      p_std=float(p.std()), init_seconds=round(elapsed, 3),
                                      reward_over_cost=replay(rows, predictions, budget, use_success=False),
                                      reward_p_over_cost=replay(rows, predictions, budget, use_success=True))
        print(mode, len(rows), result['models'][mode]['cost_mae'],
              result['models'][mode]['reward_over_cost']['points'], flush=True)
    return result


def main():
    result = dict(quality_holdout=evaluate(quality_holdout(), 15000),
                  catboost_selected=evaluate(policy_cohort(), 25000),
                  notes=['Replay assumes each task has the same outcome and cost in any order.',
                         'CatBoost-selected cohort has selection bias and omits unattempted tasks.',
                         'Quality holdout was reused for previous model analysis; older models may have seen related families.',
                         'Replay scores are not real proxy scores. No references are used as predictor inputs.'])
    path = REPORT / 'all-predictors-retrospective.json'
    path.write_text(json.dumps(result, indent=2) + '\n', encoding='utf-8')
    print(path, flush=True)


if __name__ == '__main__':
    main()
