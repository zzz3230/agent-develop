"""Run reference-free benchmark jobs through the real stock OJ agent.

Input tasks must have no expected field. Judge outputs separately on the host.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import shutil
import sys
import tempfile
import time
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


async def run(root: Path, output: Path, limit: float) -> None:
    from runtime.budget import Budget, Journal
    from runtime.metered_model import MeteredModel
    from runtime.oj_agent import Connection, react_agent
    from runtime.tasks import load_task

    connection = Connection(os.environ['LLM_BASE_URL'], os.environ.pop('LLM_API_KEY'))
    journal = Journal(output / 'usage.jsonl')
    budget = Budget(limit, journal)
    # Evaluation uses reported usage exactly when available; the production
    # meter currently takes max(reported, character estimate), biasing comparisons.
    def exact_charge(self, messages, tools, message):
        usage = getattr(message, 'usage_metadata', None)
        inp = int(getattr(usage, 'input_tokens', 0) or 0)
        out = int(getattr(usage, 'output_tokens', 0) or 0)
        if inp and out:
            self._budget.charge(self._name, inp, out, False)
        else:
            original(self, messages, tools, message)
    original = MeteredModel._charge
    MeteredModel._charge = exact_charge
    jobs = json.loads((root / 'jobs.json').read_text())
    prior = output / 'results.jsonl'
    existing = [json.loads(line) for line in prior.read_text().splitlines()] if prior.exists() else []
    completed = {row['id'] for row in existing}
    budget.spent = sum(row['cost'] for row in existing)
    consecutive_errors = 0
    for job in jobs:
        if job['id'] in completed:
            continue
        if budget.remaining() < 1500:
            break
        identifier = job['id']
        work = output / 'tasks' / identifier
        shutil.copytree(root / 'tasks' / job['task'], work)
        task = load_task(work)
        assert 'expected' not in json.loads((work / 'task.json').read_text())
        budget.begin_task(identifier, 3000)
        started = time.monotonic()
        row = {**job, 'error': None, 'answer': '', 'tests_unchanged': True}
        tests = {p: p.read_bytes() for p in task.cwd.rglob('test_*.py')}
        try:
            query = task.query
            if job.get('schema'):
                from runtime.sql_tables import describe
                try:
                    query += '\nCSV schema (all columns TEXT):\n' + describe(task.cwd)
                except (ValueError, OSError) as exc:
                    query += '\nCSV schema unavailable; use Python: ' + str(exc)
            prompt = job.get('system_prompt')
            if job.get('sql'):
                from runtime.sql_profile import SQL_SYSTEM
                prompt = SQL_SYSTEM
            agent = react_agent(budget, connection, job['model'], str(task.cwd),
                                tuple(job['tools']), max_steps=6, max_output=1200,
                                compact=job.get('compact', True), system_prompt=prompt)
            if job.get('sql'):
                from runtime.sql_profile import SqlCompletionRail
                await agent.register_rail(SqlCompletionRail())
            result = await asyncio.wait_for(agent.invoke({'query': query,
                'conversation_id': uuid.uuid4().hex}), timeout=150)
            row['answer'] = str(result.get('output', '') if isinstance(result, dict) else result).strip()
        except Exception as exc:
            row['error'] = f'{type(exc).__name__}: {exc}'[:500]
        finally:
            row['tests_unchanged'] = all(p.exists() and p.read_bytes() == data for p, data in tests.items())
            for p, data in tests.items():
                p.write_bytes(data)
        row['cost'] = round(budget.end_task(), 2)
        row['seconds'] = round(time.monotonic() - started, 2)
        with (output / 'results.jsonl').open('a') as stream:
            stream.write(json.dumps(row, ensure_ascii=False) + '\n')
        print('BENCH', json.dumps(row, ensure_ascii=False), flush=True)
        completed.add(identifier)
        consecutive_errors = consecutive_errors + 1 if row['error'] else 0
        if consecutive_errors >= 4:
            break
    journal.write('benchmark_finish', spent=budget.spent, requested=len(jobs), completed=len(completed))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--input', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--budget', type=float, default=30000)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    os.chdir(tempfile.mkdtemp(prefix='oj-benchmark-'))
    asyncio.run(run(args.input.resolve(), args.output.resolve(), args.budget))


if __name__ == '__main__':
    main()
