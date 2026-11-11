"""Base vs ready changes on the same tasks and budget, one change at a time (no full grid).

    python -m evaluation.compare_changes --suite /tmp/suite/dev --budget 30000 --out /tmp/cmp

BUDGET is enforced here (ENFORCE_BUDGET=1): a variant stops at it like the proxy cutting the key,
so order and spend actually matter. Needs LLM_BASE_URL and LLM_API_KEY (or evaluation/mock_llm.py for a dry run). Every variant
gets a fresh copy of SUITE/input, its own trajectory and an independent evaluation.grade report.
Use the dev split while tuning; the holdout split only for the final measurement.
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

from evaluation.grade import grade

ROOT = Path(__file__).resolve().parents[1]
BASE = dict(QUEUE='0', RETRY='0', PROMPT_ECONOMY='0', ADAPTIVE_LIMITS='0', CSV_SCHEMA='0', SEARCH_CONTEXT='0', CSV_SQL='0')
VARIANTS = {
    'base': {},
    '+instructions': dict(PROMPT_ECONOMY='1'),
    '+adaptive_stops': dict(ADAPTIVE_LIMITS='1'),
    '+csv_search_prep': dict(CSV_SCHEMA='1', SEARCH_CONTEXT='1'),
    '+queue': dict(QUEUE='1'),
    'all_on': dict(PROMPT_ECONOMY='1', ADAPTIVE_LIMITS='1', CSV_SCHEMA='1', SEARCH_CONTEXT='1', QUEUE='1'),
}


def run_variant(name, extra, suite, out, budget):
    work = out / name.strip('+')
    shutil.rmtree(work, ignore_errors=True)
    shutil.copytree(suite / 'input', work / 'tasks')
    env = {**os.environ, **BASE, **extra, 'BUDGET': str(budget), 'ENFORCE_BUDGET': '1', 'TRAJECTORY': str(work / 'trajectory.jsonl')}
    started = time.monotonic()
    with open(work / 'console.log', 'w', encoding='utf-8') as log:
        subprocess.run([sys.executable, str(ROOT / 'run_agent.py'), '--tasks-dir', str(work / 'tasks')],
                       env=env, stdout=log, stderr=subprocess.STDOUT, check=False)
    report = grade(suite, work / 'tasks', work / 'trajectory.jsonl')
    (work / 'graded.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    total = report['total']
    return dict(variant=name, points=total['points'], possible=total['possible'], solved=total['correct'],
                false_claims=total['false_claims'], spent=report['spent'],
                seconds=report['seconds'] or round(time.monotonic() - started, 1),
                stop=report.get('stop') or 'no finish event, see console.log')


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--suite', type=Path, required=True)
    parser.add_argument('--budget', type=float, default=100000)
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--only', nargs='*', choices=list(VARIANTS))
    args = parser.parse_args()
    missing = [k for k in ('LLM_BASE_URL', 'LLM_API_KEY') if not os.environ.get(k)]
    if missing:
        parser.error('set ' + ' and '.join(missing) + ' in this terminal first')
    args.out.mkdir(parents=True, exist_ok=True)
    rows = [run_variant(name, VARIANTS[name], args.suite, args.out, args.budget) for name in (args.only or VARIANTS)]
    (args.out / 'summary.json').write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding='utf-8')
    base = next((r for r in rows if r['variant'] == 'base'), None)
    print(f'Results: {args.out.resolve()}')
    print('| Вариант | Баллы | Решено | Ложные ответы | Расход | Время, с | Δ баллов к базе | Остановка |')
    print('|---|---:|---:|---:|---:|---:|---:|---|')
    for r in rows:
        delta = r['points'] - base['points'] if base else ''
        print(f"| {r['variant']} | {r['points']}/{r['possible']} | {r['solved']} | {r['false_claims']} | "
              f"{r['spent']} | {r['seconds']} | {delta} | {r['stop']} |")


if __name__ == '__main__':
    main()
