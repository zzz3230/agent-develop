"""Three paired 200-task trials: reward/cost, reward*p/cost, reward/cost+precheck."""
import hashlib
import json
from pathlib import Path

from evaluation.compare_pool_predictors import summarize
from evaluation.quality_dataset import ROOT, WORK, dump, input_hash
from evaluation.run_image import image_id, run

IMAGE = 'agent-develop:catboost-compare'
SUITE = ROOT / 'benchmarks/quality-holdout-200'
ORDER = WORK / 'order-101'
OUT = ROOT / 'benchmark-runs/catboost-policy-200-50k'
POLICIES = (('cost_only', '0', '0'), ('success_cost', '1', '0'), ('cost_precheck', '0', '1'))


def main():
    manifest = json.loads((SUITE / 'manifest.json').read_text(encoding='utf-8'))
    assert input_hash(SUITE / 'input') == manifest['input_sha256']
    assert input_hash(ORDER) == json.loads((WORK / 'comparison/protocol.json').read_text(encoding='utf-8'))['input_sha256']
    OUT.mkdir(parents=True, exist_ok=True)
    model_hashes = {name: hashlib.sha256((ROOT / 'predictors' / f'catboost_structural_{name}.cbm').read_bytes()).hexdigest()
                    for name in ('success', 'cost')}
    protocol = dict(image=IMAGE, image_id=image_id(IMAGE), tasks=200, max_points=manifest.get('max_points'),
                    budget=50000, input_sha256=input_hash(ORDER), models=model_hashes,
                    policies=[dict(name=n, use_success=p, precheck=pre) for n, p, pre in POLICIES],
                    common=dict(PREDICTOR='catboost_structural', QUEUE='1', QUEUE_POLICY='greedy',
                                SCORE_ALPHA='1', RETRY='0', BUDGET='50000', ENFORCE_BUDGET='1',
                                IMPOSSIBLE_NUDGE='1'))
    path = OUT / 'protocol.json'
    if path.exists():
        assert json.loads(path.read_text(encoding='utf-8')) == protocol
    else:
        dump(path, protocol)
    rows = []
    for name, use_success, precheck in POLICIES:
        target = OUT / name
        if not (target / 'graded.json').exists():
            print('START', name, flush=True)
            run(IMAGE, ORDER, target, env={**protocol['common'], 'QUEUE_USE_SUCCESS': use_success,
                                          'PRECHECK': precheck}, hard_budget=50000, references=SUITE,
                quiet=True, wall_limit=3600)
        row = summarize(target)
        assert row['exit_code'] in (0, 137) and (row['spent'] >= 50000 or row['completed'] == 200)
        row['name'] = name
        rows.append(row)
        dump(OUT / 'results.json', rows)
        print('RESULT', json.dumps(row), flush=True)


if __name__ == '__main__':
    main()
