"""AGE-6 spike: run one task through a stock OJ agent and report what it costs.

Usage: spike_oj.py VARIANT WORKSPACE
VARIANT: deep | react-all | react-all-compact | react-bash | react-bash-compact | react-coding-compact
"""
from __future__ import annotations

import asyncio
import os
import sys
import tempfile
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
workspace = str(Path(sys.argv[2]).resolve())
os.chdir(tempfile.mkdtemp(prefix="agent-"))  # OJ creates logs/ in the current directory

from runtime.budget import Budget, Journal  # noqa: E402
from runtime.oj_agent import Connection, deep_agent, react_agent  # noqa: E402

QUERY = "A warehouse starts with 1669 boxes. It ships 36 boxes per day for 3 days. How many boxes are left?"
MODEL = os.environ.get("SPIKE_MODEL", "qwen3.8-27b-noreason")
ALL = ("read", "write", "edit", "list", "grep", "bash")
VARIANTS = {
    "react-all": (ALL, False), "react-all-compact": (ALL, True),
    "react-bash": (("bash",), False), "react-bash-compact": (("bash",), True),
    "react-coding-compact": (("bash", "read", "edit"), True),
}


async def main() -> None:
    budget = Budget(100_000, Journal(Path("/tmp/spike.jsonl")))
    budget.begin_task("spike", float("inf"))
    connection, variant = Connection(os.environ["LLM_BASE_URL"], os.environ["LLM_API_KEY"]), sys.argv[1]
    if variant == "deep":
        agent = deep_agent(budget, connection, MODEL, workspace, 4, 500)
    else:
        tools, compact = VARIANTS[variant]
        agent = react_agent(budget, connection, MODEL, workspace, tools, 4, 500, compact=compact)
    result = await agent.invoke({"query": QUERY, "conversation_id": uuid.uuid4().hex})
    print("RESULT", variant, result.get("output"), "SPENT", round(budget.spent, 1), "FILES", len(list(Path(workspace).rglob("*"))))


asyncio.run(main())
