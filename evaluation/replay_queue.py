"""Replay recorded per-task attempts under one shared budget: baseline order vs TaskQueue.

Input: graded rows (id, type, reward, status, correct, cost, seconds) from a real proxy run,
e.g. docs/benchmarks/stock-oj-100/ours-graded.json. The queue sees only what the harness
sees at run time (type, reward, own status, measured cost); `correct` is used for scoring only.

Assumption: a task costs the same and ends the same regardless of its position
(temperature 0, independent workspaces). The proxy cuts the run when the budget is
exceeded; the task crossing the limit earns nothing. Retries cannot be replayed
(there are no recorded second attempts), so RETRY stays outside this measurement.
"""
from __future__ import annotations

import argparse
import json
import random
import statistics
import sys
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from runtime.task_queue import TaskQueue  # noqa: E402


def simulate(rows, budget, enabled, known_budget=True, time_limit=3300.0):
    tasks = [SimpleNamespace(id=r['id'], type=r['type'], reward=float(r['reward'])) for r in rows]
    by_id = {r['id']: r for r in rows}
    queue = TaskQueue(tasks, enabled=enabled)
    spent = seconds = points = 0.0
    solved = attempted = 0
    order = []
    while True:
        pick = queue.next(max(0.0, budget - spent) if known_budget else None)
        if pick is None:
            break
        task, _ = pick
        row = by_id[task.id]
        if spent + row['cost'] > budget or seconds + row.get('seconds', 0) > time_limit:
            spent = min(budget, spent + row['cost'])  # proxy stops answering mid-task
            break
        spent += row['cost']
        seconds += row.get('seconds', 0)
        attempted += 1
        order.append(task.id)
        if row['correct']:
            solved += 1
            points += row['reward']
        queue.record(task, row['status'], row['cost'], row.get('error') or '')
    return dict(points=points, solved=solved, attempted=attempted, spent=round(spent, 1),
                seconds=round(seconds, 1), order=order)


def report(rows, budgets, permutations, seed, known_budget):
    out = []
    rng = random.Random(seed)
    orders = [list(rows)] + [rng.sample(rows, len(rows)) for _ in range(permutations)]
    for budget in budgets:
        base = [simulate(o, budget, False, known_budget) for o in orders]
        queue = [simulate(o, budget, True, known_budget) for o in orders]
        wins = sum(q['points'] > b['points'] for b, q in zip(base, queue))
        ties = sum(q['points'] == b['points'] for b, q in zip(base, queue))
        mean = lambda xs, k: round(statistics.mean(x[k] for x in xs), 1)  # noqa: E731
        out.append(dict(
            budget=budget, known_budget=known_budget, orders=len(orders),
            recorded_order=dict(base=base[0]['points'], queue=queue[0]['points'],
                                base_solved=base[0]['solved'], queue_solved=queue[0]['solved'],
                                base_seconds=base[0]['seconds'], queue_seconds=queue[0]['seconds']),
            mean_points=dict(base=mean(base, 'points'), queue=mean(queue, 'points')),
            min_points=dict(base=min(b['points'] for b in base), queue=min(q['points'] for q in queue)),
            mean_solved=dict(base=mean(base, 'solved'), queue=mean(queue, 'solved')),
            mean_attempted=dict(base=mean(base, 'attempted'), queue=mean(queue, 'attempted')),
            mean_spent=dict(base=mean(base, 'spent'), queue=mean(queue, 'spent')),
            mean_seconds=dict(base=mean(base, 'seconds'), queue=mean(queue, 'seconds')),
            queue_wins=wins, ties=ties, queue_losses=len(orders) - wins - ties,
        ))
    return out


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--graded', type=Path, nargs='+',
                        default=[Path('docs/benchmarks/stock-oj-100/ours-graded.json')])
    parser.add_argument('--budgets', type=float, nargs='+', default=[30000, 50000, 100000, 150000])
    parser.add_argument('--permutations', type=int, default=200)
    parser.add_argument('--seed', type=int, default=12)
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    result = {}
    for path in args.graded:
        rows = json.loads(path.read_text(encoding='utf-8'))['rows']
        result[path.name] = (report(rows, args.budgets, args.permutations, args.seed, True)
                             + report(rows, [100000], args.permutations, args.seed, False))
    text = json.dumps(result, ensure_ascii=False, indent=1)
    if args.output:
        args.output.write_text(text + '\n', encoding='utf-8')
    print(text)


if __name__ == '__main__':
    main()
