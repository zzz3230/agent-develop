"""Repeat the best measured predictor beside a reward-descending task order."""
import hashlib
import json
import shutil

from evaluation.compare_pool_predictors import summarize
from evaluation.predictor_experiment import ROOT
from evaluation.quality_dataset import dump, input_hash
from evaluation.run_image import image_id, run

SUITE = ROOT / 'benchmark-runs/planner-200-eval-101-v2'
PAST = ROOT / 'docs/results/pool200-50k-v1/results.json'
NEW = ROOT / 'benchmark-runs/catboost-old-comparison-200-50k'
OUT = ROOT / 'benchmark-runs/best-vs-reward-latest-200-50k'
ORDER = ROOT / 'benchmark-runs/best-vs-reward-200-50k/reward-order'
BUDGET = 50000


def prepare_order():
    manifest = json.loads((SUITE / 'manifest.json').read_text(encoding='utf-8'))
    indexed = []
    for directory in sorted((SUITE / 'input').iterdir()):
        if not (directory / 'task.json').is_file():
            continue
        task = json.loads((directory / 'task.json').read_text(encoding='utf-8'))
        indexed.append((directory, task))
    assert len(indexed) == 200
    indexed.sort(key=lambda pair: -float(pair[1]['reward']))
    if not ORDER.exists():
        ORDER.mkdir(parents=True)
        for index, (directory, task) in enumerate(indexed):
            shutil.copytree(directory, ORDER / f'{index:04}_{task["task_id"]}')
    assert len(list(ORDER.glob('*/task.json'))) == 200
    expected = [task['task_id'] for _, task in indexed]
    observed = [json.loads(p.read_text(encoding='utf-8'))['task_id'] for p in sorted(ORDER.glob('*/task.json'))]
    assert observed == expected
    return input_hash(ORDER), expected


def choose_best():
    old = json.loads(PAST.read_text(encoding='utf-8'))['results']
    candidates = [r for r in old if r['policy'] == 'greedy']
    large = summarize(NEW)
    assert large['mode'] == 'catboost_large' and large['spent'] >= BUDGET
    candidates.append(large)
    best = max(candidates, key=lambda r: (r['strict_points'], -r['spent']))
    return best, candidates


def main():
    source_hash, order = prepare_order()
    best, candidates = choose_best()
    image = 'agent-develop:catboost-large'
    common = dict(QUEUE_POLICY='greedy', SCORE_ALPHA='1', RETRY='0', BUDGET=str(BUDGET),
                  ENFORCE_BUDGET='1', QUEUE_USE_SUCCESS='0', TIGHT_CAPS='1',
                  SEARCH_PROGRESS='entity', STAY_INSIDE='1', PROGRESS_STRICT='1',
                  CODING_PRECHECK='1', SHELL_EXTRA='1', PRECHECK='1', IMPOSSIBLE_NUDGE='1')
    protocol = dict(source_input_sha256=input_hash(SUITE / 'input'), reward_order_sha256=source_hash,
                    order_ids_sha256=hashlib.sha256(json.dumps(order).encode()).hexdigest(),
                    selected=best['mode'], selected_previous_points=best['strict_points'],
                    candidates={r['mode']: r['strict_points'] for r in candidates}, image=image,
                    image_id=image_id(image), budget=BUDGET,
                    note='Model was selected using older-agent trials on this workload. Both final runs '
                         'use the latest main image plus the selected predictor; local weighted token '
                         'accounting may differ from the contest proxy.')
    OUT.mkdir(parents=True, exist_ok=True)
    path = OUT / 'protocol.json'
    if path.exists():
        assert json.loads(path.read_text(encoding='utf-8')) == protocol
    else:
        dump(path, protocol)
    results = {}
    for name, env in [('best_predictor', {**common, 'PREDICTOR': best['mode'], 'QUEUE': '1'}),
                      ('reward_descending', {**common, 'PREDICTOR': 'baseline', 'QUEUE': '0'})]:
        target = OUT / name
        if not (target / 'graded.json').exists():
            print('START', name, best['mode'], flush=True)
            run(image, ORDER, target, env=env, hard_budget=BUDGET, wall_limit=3600,
                references=SUITE, quiet=True)
        row = summarize(target)
        assert row['exit_code'] in (0, 137) and row['spent'] >= BUDGET
        results[name] = row
        dump(OUT / 'results.json', results)
        print('RESULT', name, row['strict_points'], row['strict_correct'], row['spent'], flush=True)


if __name__ == '__main__':
    main()
