"""One fixed knapsack trial beside the latest-agent greedy and reward trials."""
import hashlib
import json

from evaluation.compare_pool_predictors import summarize
from evaluation.quality_dataset import ROOT, dump, input_hash
from evaluation.run_image import image_id, run

PAIRED = ROOT / 'benchmark-runs/best-vs-reward-latest-200-50k'
SUITE = ROOT / 'benchmark-runs/planner-200-eval-101-v2'
ORDER = ROOT / 'benchmark-runs/best-vs-reward-200-50k/reward-order'
OUT = ROOT / 'benchmark-runs/knapsack-fixed-latest-200-50k'
IMAGE = 'agent-develop:knapsack-fixed-latest'


def main():
    paired = json.loads((PAIRED / 'protocol.json').read_text(encoding='utf-8'))
    assert paired['reward_order_sha256'] == input_hash(ORDER)
    greedy = summarize(PAIRED / 'best_predictor')
    assert greedy['mode'] == 'catboost_large' and greedy['policy'] == 'greedy'
    env = json.loads((PAIRED / 'best_predictor/run.json').read_text(encoding='utf-8'))['env']
    assert env['PREDICTOR'] == 'catboost_large' and env['QUEUE_USE_SUCCESS'] == '0'
    env = {**env, 'QUEUE_POLICY': 'knapsack'}
    protocol = dict(image=IMAGE, image_id=image_id(IMAGE), input_sha256=input_hash(ORDER),
                    source_image=paired['image'], source_image_id=paired['image_id'],
                    fixed_queue_sha256=hashlib.sha256((ROOT / 'runtime/task_queue.py').read_bytes()).hexdigest(),
                    budget=50000, env=env,
                    note='Same latest agent, task order, and predictor as greedy. This image changes only '
                         'the task_queue module to fix the knapsack objective; greedy code is unchanged.')
    OUT.mkdir(parents=True, exist_ok=True)
    path = OUT / 'protocol.json'
    if path.exists():
        assert json.loads(path.read_text(encoding='utf-8')) == protocol
    else:
        dump(path, protocol)
    if not (OUT / 'trial/graded.json').exists():
        run(IMAGE, ORDER, OUT / 'trial', env=env, hard_budget=50000,
            wall_limit=3600, references=SUITE, quiet=True)
    row = summarize(OUT / 'trial')
    assert row['exit_code'] in (0, 137) and row['spent'] >= 50000
    dump(OUT / 'result.json', row)
    print(json.dumps(row, indent=2), flush=True)


if __name__ == '__main__':
    main()
