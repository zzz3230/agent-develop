"""One missing real trial: large CatBoost beside the six archived 200/50k trials."""
import json

from evaluation.compare_pool_predictors import summarize
from evaluation.predictor_experiment import ROOT
from evaluation.run_image import run

SUITE = ROOT / 'benchmark-runs/planner-200-eval-101-v2'
OUT = ROOT / 'benchmark-runs/catboost-old-comparison-200-50k'
IMAGE = 'agent-develop:catboost-old-comparison'


def main():
    if not (OUT / 'graded.json').exists():
        run(IMAGE, SUITE / 'input', OUT,
            env=dict(PREDICTOR='catboost_large', QUEUE_POLICY='greedy', SCORE_ALPHA='1',
                     QUEUE='1', RETRY='0', BUDGET='50000', ENFORCE_BUDGET='1'),
            hard_budget=50000, wall_limit=3600, references=SUITE,
            commit='f8e23acab8083a1ae7172c05b6033b83c22ee761', quiet=True)
    row = summarize(OUT)
    assert row['exit_code'] in (0, 137) and row['spent'] >= 50000
    print(json.dumps(row, indent=2), flush=True)


if __name__ == '__main__':
    main()
