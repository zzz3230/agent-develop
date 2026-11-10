"""M1 entry point: runs tasks through the configured stock OJ agent within one shared budget.

Tasks run in directory order for now; task choice (M3) and agent tuning (M2) plug in here.
"""
from __future__ import annotations

import argparse
import asyncio
import hashlib
import os
import re
import subprocess
import sys
import tempfile
import time
import uuid
from dataclasses import asdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from runtime.budget import Budget, BudgetExhausted, Journal, TaskLimitExceeded  # noqa: E402
from runtime.tasks import Task, load_task, save_answer  # noqa: E402
from runtime.profiles import system_for_task  # noqa: E402
from runtime.attempt_policy import AttemptLimits, limits_for_task  # noqa: E402

DEFAULT_BUDGET = 100_000
TIME_LIMIT_S = 3300.0
MAX_CONSECUTIVE_ERRORS = 4
MODEL = "qwen3.8-27b-noreason"
TOOLS = {
    "math": ("bash",),
    "data_analysis": ("bash",),
    "search": ("bash",),
    # OJ 0.1.19 read_file can fail releasing its file lock in this runtime;
    # edit_file then cannot satisfy its prerequisite. Use the stock shell.
    "coding": ("bash",),
}
_TEST_COMMAND = re.compile(r"`python3? ([\w./-]+\.py)`")


def tests_pass(task: Task) -> bool:
    command = _TEST_COMMAND.search(task.instruction)
    if not command:
        return False
    done = subprocess.run(
        ["python3", "-B", command.group(1)], cwd=task.cwd, capture_output=True, timeout=30, stdin=subprocess.DEVNULL,
    )
    return done.returncode == 0


def snapshot_tests(task: Task) -> dict[Path, bytes]:
    return {path: path.read_bytes() for path in task.cwd.rglob("test_*.py")}


def restore_tests(snapshot: dict[Path, bytes]) -> bool:
    """Puts tests back; True if the agent had changed any."""
    changed = False
    for path, content in snapshot.items():
        if not path.exists() or hashlib.sha256(path.read_bytes()).digest() != hashlib.sha256(content).digest():
            path.write_bytes(content)
            changed = True
    return changed


async def attempt(task: Task, budget: Budget, connection, react_agent,
                  limits: AttemptLimits | None = None, timeout: float | None = None) -> tuple[str, str]:
    """Returns (status, answer); status is solved, impossible or failed."""
    tests = snapshot_tests(task)
    limits = limits or limits_for_task(task.type)
    query = task.query
    system_prompt = system_for_task(task.type)
    use_sql = task.type == 'data_analysis' and os.environ.get('CSV_SQL') == '1'
    use_schema = use_sql or (task.type == 'data_analysis' and os.environ.get('CSV_SCHEMA', '1') == '1')
    if use_schema:
        import sqlite3
        from runtime.sql_tables import describe
        try:
            schema = describe(task.cwd)
            if len(schema) > 12000:
                raise ValueError('CSV schema too large; using regular agent')
            query += '\nCSV schema (all columns TEXT):\n' + schema
            if use_sql:
                from runtime.sql_profile import SQL_SYSTEM, SqlCompletionRail
                system_prompt = SQL_SYSTEM
        except (ValueError, OSError, sqlite3.Error) as exc:
            use_sql = use_schema = False
            budget.journal.write('sql_schema_fallback', task=task.id, error=str(exc)[:300])
    if task.type == 'search' and os.environ.get('SEARCH_CONTEXT', '1') == '1':
        from runtime.search_context import search_context
        context = search_context(task.cwd, task.query)
        if context:
            query += '\n' + context
    agent = react_agent(
        budget, connection, MODEL, str(task.cwd), TOOLS.get(task.type, ("bash",)), max_steps=limits.steps,
        max_output=limits.output_tokens, system_prompt=system_prompt,
    )
    from runtime.attempt_rail import AttemptRail
    await agent.register_rail(AttemptRail(task.cwd, limits, budget.journal, budget, task.type))
    if use_sql:
        await agent.register_rail(SqlCompletionRail())
    invocation_error = None
    result = {}
    try:
        result = await asyncio.wait_for(
            agent.invoke({"query": query, "conversation_id": uuid.uuid4().hex}),
            timeout=limits.seconds if timeout is None else min(timeout, limits.seconds),
        )
    except Exception as exc:
        invocation_error = exc
    finally:
        edited_tests = restore_tests(tests)
        (task.cwd / 'answer.txt').unlink(missing_ok=True)
    final = str(result.get("output", "") if isinstance(result, dict) else result).strip()
    if edited_tests:
        return "failed", "agent edited the tests"
    if task.type == 'coding' and tests_pass(task):
        return 'solved', 'DONE'
    if invocation_error is not None:
        raise invocation_error
    if isinstance(result, dict) and result.get('stop_reason'):
        return 'failed', str(result['stop_reason'])
    if final == 'Max iterations reached without completion':
        return 'failed', 'step limit'
    if re.search(r"\bIMPOSSIBLE\b", final):
        return "impossible", ""
    if task.type == "coding":
        return 'failed', 'tests still fail'
    answer = final.splitlines()[-1].strip() if final else ""
    if task.check == 'exact_int' and not re.fullmatch(r'[+-]?\d+', answer):
        return 'failed', 'invalid integer answer'
    return ("solved", answer) if answer else ("failed", "empty answer")


async def run(tasks: list[Task], budget: Budget, journal: Journal, deadline: float) -> str:
    from runtime.oj_agent import Connection, react_agent  # OJ needs a writable current directory

    connection = Connection(os.environ["LLM_BASE_URL"], os.environ.pop("LLM_API_KEY"))  # out of reach of agent shells
    errors = 0
    for task in tasks:
        if time.monotonic() > deadline:
            return "time limit"
        limits = limits_for_task(task.type)
        budget.begin_task(task.id, min(limits.initial_cost, limits.cost), hard_limit=limits.cost)
        journal.write('attempt_start', task=task.id, limits=asdict(limits))
        stop = None
        try:
            status, detail = await attempt(task, budget, connection, react_agent, limits,
                                           timeout=max(0.0, deadline-time.monotonic()))
            errors = 0
        except BudgetExhausted:
            status, detail, stop = 'failed', 'budget exhausted', 'budget exhausted'
        except TaskLimitExceeded:
            status, detail = 'failed', 'task cost limit'
            errors = 0
        except (asyncio.TimeoutError, subprocess.TimeoutExpired):
            status, detail = 'failed', 'task time limit'
            errors = 0
        except Exception as exc:  # one failed task must not end the run
            errors += 1
            status, detail = "failed", f"{type(exc).__name__}: {exc}"[:300]
        if status == "solved":
            save_answer(task, detail)
        journal.write("outcome", task=task.id, type=task.type, reward=task.reward, status=status,
                      detail=detail, cost=round(budget.end_task(), 1))
        if stop:
            return stop
        if errors >= MAX_CONSECUTIVE_ERRORS:
            return "model API keeps failing"
    return "all tasks handled"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--tasks-dir", default=os.environ.get("TASKS", "/data/tasks"))
    args = parser.parse_args()

    started = time.monotonic()
    root = Path(args.tasks_dir).resolve()
    os.chdir(tempfile.mkdtemp(prefix="agent-"))  # OJ creates logs/ here; the image root is read-only
    journal = Journal(Path(os.environ.get("TRAJECTORY", "/tmp/harness/trajectory.jsonl")))
    budget = Budget(float(os.environ.get("BUDGET") or DEFAULT_BUDGET), journal)

    tasks: list[Task] = []
    for directory in sorted(p for p in root.iterdir() if (p / "task.json").is_file()):
        try:
            tasks.append(load_task(directory))
        except (OSError, ValueError, KeyError) as exc:
            journal.write("bad_task", dir=directory.name, error=repr(exc))
    journal.write("start", tasks=len(tasks), budget_estimate=budget.total, budget_authority='proxy')
    try:
        stop = asyncio.run(run(tasks, budget, journal, started + TIME_LIMIT_S))
    except Exception as exc:
        stop = f"{type(exc).__name__}: {exc}"[:300]
    journal.write("finish", spent=round(budget.spent, 1), seconds=round(time.monotonic() - started, 1), stop=stop)
    return 0


if __name__ == "__main__":
    sys.exit(main())
