"""Strict score curves at local token cutoffs, using recorded real attempts."""
import json

from evaluation.quality_dataset import ROOT, dump

ROOT_RUN = ROOT / 'benchmark-runs/best-vs-reward-latest-200-50k'
CUTOFFS = (10000, 14285.7, 20000, 30000, 50000)


def summarize(target):
    graded = json.loads((target / 'graded.json').read_text(encoding='utf-8'))
    by_id = {r['id']: r for r in graded['rows']}
    spent = 0.0
    outcomes = []
    for line in (target / 'harness/trajectory.jsonl').read_text(encoding='utf-8').splitlines():
        row = json.loads(line)
        if row['event'] == 'llm_call':
            spent += float(row['cost'])
        elif row['event'] == 'outcome':
            outcomes.append((spent, row['task']))
    result = {}
    for cutoff in CUTOFFS:
        eligible = [task for cost, task in outcomes if cost <= cutoff + 1e-6]
        assert len(eligible) == len(set(eligible))
        result[str(cutoff)] = dict(points=sum(by_id[t]['points'] for t in eligible),
                                   correct=sum(bool(by_id[t]['correct']) for t in eligible),
                                   completed=len(eligible),
                                   last_completed_cost=max((cost for cost, task in outcomes if cost <= cutoff),
                                                           default=0.0))
    return result


def main():
    result = dict(assumption='A common multiplier on every task; local cutoffs are approximations '
                             'to proxy budget, not proxy measurements.',
                  cutoffs=list(CUTOFFS),
                  best_predictor=summarize(ROOT_RUN / 'best_predictor'),
                  reward_descending=summarize(ROOT_RUN / 'reward_descending'))
    knapsack = ROOT / 'benchmark-runs/knapsack-fixed-latest-200-50k/trial'
    if (knapsack / 'graded.json').exists():
        result['knapsack'] = summarize(knapsack)
    instruction = ROOT / 'benchmark-runs/catboost-instruction-full-200-50k/trial'
    if (instruction / 'graded.json').exists():
        result['catboost_instruction'] = summarize(instruction)
    path = ROOT / 'docs/results/quality-minilm-v1/best-vs-reward-sensitivity.json'
    dump(path, result)
    print(json.dumps(result, indent=2), flush=True)


if __name__ == '__main__':
    main()
