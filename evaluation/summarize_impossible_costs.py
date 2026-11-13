"""Audit true impossibility, agent abstentions and weighted-token costs.

Reads graded results only; never calls the proxy. Tasks not reached because of
the benchmark budget are reported separately from explicit abstentions.
"""
import json
from pathlib import Path

from evaluation.quality_dataset import ROOT, dump


RUNS = {
    'catboost_large_greedy': ROOT/'benchmark-runs/best-vs-reward-latest-200-50k/best_predictor',
    'reward_only': ROOT/'benchmark-runs/best-vs-reward-latest-200-50k/reward_descending',
    'catboost_large_knapsack': ROOT/'benchmark-runs/knapsack-fixed-latest-200-50k/trial',
    'catboost_instruction_greedy': ROOT/'benchmark-runs/catboost-instruction-full-200-50k/trial',
}
REPORT = ROOT/'docs/results/quality-minilm-v1/impossible-costs.json'


def summarize(path):
    data=json.loads((path/'graded.json').read_text(encoding='utf-8'))
    rows=data['rows']
    by_id={r['id']:r for r in rows}
    trajectory=path/'harness/trajectory.jsonl'
    suspects={event['task'] for line in trajectory.read_text(encoding='utf-8').splitlines() if line
              if (event:=json.loads(line)).get('event')=='precheck_suspect'}
    attempted=[r for r in rows if r['cost']>0]
    possible=[r for r in attempted if r['solvable']]
    impossible=[r for r in attempted if not r['solvable']]
    possible_mean=sum(r['cost'] for r in possible)/len(possible)
    impossible_mean=sum(r['cost'] for r in impossible)/len(impossible)
    return dict(tasks=len(rows),attempted=len(attempted),
                true_impossible_total=sum(not r['solvable'] for r in rows),
                true_impossible_attempted=len(impossible),
                true_impossible_unattempted=sum(not r['solvable'] and r['cost']==0 for r in rows),
                true_impossible_started_unfinished=sum(r['journal_status']=='not_run' for r in impossible),
                true_impossible_declared_impossible=sum(r['journal_status']=='impossible' for r in impossible),
                true_impossible_failed=sum(r['journal_status']=='failed' for r in impossible),
                true_impossible_claimed_solved=sum(r['journal_status']=='solved' for r in impossible),
                true_impossible_no_answer_after_attempt=sum(r['answer'] is None for r in impossible),
                precheck_true_impossible=sum(not by_id[t]['solvable'] for t in suspects),
                precheck_false_suspect=sum(by_id[t]['solvable'] for t in suspects),
                precheck_true_impossible_unattempted=sum(not by_id[t]['solvable'] and by_id[t]['cost']==0
                                                         for t in suspects),
                solvable_attempted=len(possible),
                solvable_declared_impossible=sum(r['journal_status']=='impossible' for r in possible),
                mean_cost_solvable=possible_mean,
                mean_cost_impossible=impossible_mean,
                impossible_cost_percent_of_solvable=100*impossible_mean/possible_mean,
                impossible_cost_share_percent=100*sum(r['cost'] for r in impossible)/sum(r['cost'] for r in attempted),
                spent=sum(r['cost'] for r in attempted))


def main():
    result={name:summarize(path) for name,path in RUNS.items()}
    assert len({v['tasks'] for v in result.values()})==1
    assert len({v['true_impossible_total'] for v in result.values()})==1
    dump(REPORT,result)
    print(json.dumps(result,indent=2),flush=True)


if __name__=='__main__':main()
