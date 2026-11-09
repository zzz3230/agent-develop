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
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from runtime.budget import Budget, BudgetExhausted, Journal  # noqa: E402
from runtime.tasks import Task, load_task, save_answer  # noqa: E402

DEFAULT_BUDGET = 100_000
TIME_LIMIT_S = 3300.0
TASK_TIME_LIMIT_S = 180.0
TASK_COST_LIMIT = 2500.0
MAX_CONSECUTIVE_ERRORS = 4
MODEL = "qwen3.8-27b-noreason"
TOOLS = {
    "math": ("bash",),
    "data_analysis": ("bash",),
    "search": ("bash",),
    "coding": ("bash", "read", "edit"),
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
    return {path: path.read_bytes() for path in task.cwd.glob("test_*.py")}


def restore_tests(snapshot: dict[Path, bytes]) -> bool:
    """Puts tests back; True if the agent had changed any."""
    changed = False
    for path, content in snapshot.items():
        if not path.exists() or hashlib.sha256(path.read_bytes()).digest() != hashlib.sha256(content).digest():
            path.write_bytes(content)
            changed = True
    return changed


async def attempt(task: Task, budget: Budget, connection, react_agent) -> tuple[str, str]:
    """Returns (status, answer); status is solved, impossible or failed."""
    tests = snapshot_tests(task)
    agent = react_agent(
        budget, connection, MODEL, str(task.cwd), TOOLS.get(task.type, ("bash",)), max_steps=6, max_output=600,
    )
    result = await asyncio.wait_for(
        agent.invoke({"query": task.query, "conversation_id": uuid.uuid4().hex}), timeout=TASK_TIME_LIMIT_S,
    )
    (task.cwd / "answer.txt").unlink(missing_ok=True)  # only the harness writes the graded file
    final = str(result.get("output", "") if isinstance(result, dict) else result).strip()
    if restore_tests(tests):
        return "failed", "agent edited the tests"
    if re.search(r"\bIMPOSSIBLE\b", final):
        return "impossible", ""
    if task.type == "coding":
        return ("solved", "DONE") if tests_pass(task) else ("failed", "tests still fail")
    answer = final.splitlines()[-1].strip() if final else ""
    return ("solved", answer) if answer else ("failed", "empty answer")


async def run(tasks: list[Task], budget: Budget, journal: Journal, deadline: float) -> str:
    from runtime.oj_agent import Connection, react_agent  # OJ needs a writable current directory

    connection = Connection(os.environ["LLM_BASE_URL"], os.environ.pop("LLM_API_KEY"))  # out of reach of agent shells
    errors = 0
    for task in tasks:
        if time.monotonic() > deadline:
            return "time limit"
        budget.begin_task(task.id, TASK_COST_LIMIT)
        try:
            status, detail = await attempt(task, budget, connection, react_agent)
            errors = 0
        except BudgetExhausted:
            return "budget exhausted"
        except Exception as exc:  # one failed task must not end the run
            errors += 1
            status, detail = "failed", f"{type(exc).__name__}: {exc}"[:300]
        if status == "solved":
            save_answer(task, detail)
        journal.write("outcome", task=task.id, type=task.type, reward=task.reward, status=status,
                      detail=detail, cost=round(budget.end_task(), 1))
        if budget.remaining() <= 0:
            return "budget exhausted"
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
    journal.write("start", tasks=len(tasks), budget=budget.total)
    try:
        stop = asyncio.run(run(tasks, budget, journal, started + TIME_LIMIT_S))
    except Exception as exc:
        stop = f"{type(exc).__name__}: {exc}"[:300]
    journal.write("finish", spent=round(budget.spent, 1), seconds=round(time.monotonic() - started, 1), stop=stop)
    return 0


if __name__ == "__main__":
    sys.exit(main())
