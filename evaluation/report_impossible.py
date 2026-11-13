"""Spend on impossible tasks versus solvable ones, from evaluation.grade --json reports.

    python -m evaluation.report_impossible LABEL=graded.json [LABEL=graded.json ...]
"""
import json
import sys
from pathlib import Path


def summary(report: dict) -> dict:
    rows = report['rows']
    impossible = [r for r in rows if not r['solvable']]
    solvable = [r for r in rows if r['solvable']]
    imp_cost = sum(r['cost'] or 0 for r in impossible)
    sol_cost = sum(r['cost'] or 0 for r in solvable)
    solved = [r for r in solvable if r['correct']]
    return {
        'points': report['total']['points'],
        'possible': report['total']['possible'],
        'correct': report['total']['correct'],
        'spent': round(imp_cost + sol_cost),
        'imp_cost': round(imp_cost),
        'sol_cost': round(sol_cost),
        'per_impossible': round(imp_cost / max(1, len(impossible))),
        'per_solvable': round(sol_cost / max(1, len(solvable))),
        'imp_share': round(imp_cost / max(1, imp_cost + sol_cost), 3),
        'recognized': sum(r['journal_status'] == 'impossible' for r in impossible),
        'false_claims': report['total']['false_claims'],
        'false_impossible': sum(r['journal_status'] == 'impossible' for r in solvable),
        'solved_cost_max': max((r['cost'] or 0 for r in solved), default=0),
    }


def main(argv: list[str]) -> int:
    columns = ('points', 'correct', 'spent', 'imp_cost', 'per_impossible', 'per_solvable', 'imp_share',
               'recognized', 'false_claims', 'false_impossible')
    print('label'.ljust(22) + ''.join(c[:14].rjust(15) for c in columns))
    for item in argv:
        label, _, path = item.partition('=')
        s = summary(json.loads(Path(path).read_text(encoding='utf-8')))
        print(label.ljust(22) + ''.join(str(s[c]).rjust(15) for c in columns))
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
