"""Reading tasks and saving answers; the contest's format, which OJ knows nothing about."""
from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass
from pathlib import Path

_TAIL = re.compile(r"\s*When you are done, write ONLY.*$", re.S)


@dataclass(frozen=True)
class Task:
    """No `expected` or `check` here: the agent must not see them."""
    id: str
    type: str
    instruction: str
    reward: float
    dir: Path

    @property
    def cwd(self) -> Path:
        workspace = self.dir / "workspace"
        return workspace if workspace.is_dir() else self.dir

    @property
    def query(self) -> str:
        """The instruction without the part about answer.txt, which the harness handles."""
        return _TAIL.sub("", self.instruction).strip()


def load_task(directory: Path) -> Task:
    raw = json.loads((directory / "task.json").read_text(encoding="utf-8"))
    return Task(
        id=str(raw.get("task_id") or directory.name), type=str(raw["task_type"]),
        instruction=str(raw["instruction"]), reward=float(raw.get("reward", 0)), dir=directory,
    )


def save_answer(task: Task, answer: str) -> None:
    """Atomic and synced: a finished answer survives a hard kill right after this returns."""
    target = task.dir / "answer.txt"
    temporary = task.dir / ".answer.tmp"
    with temporary.open("w", encoding="utf-8") as f:
        f.write(f"{answer.strip()}\n")
        f.flush()
        os.fsync(f.fileno())
    os.replace(temporary, target)
