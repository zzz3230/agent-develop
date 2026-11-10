"""The single token meter and the run journal."""
from __future__ import annotations

import json
import sys
import threading
import time
from pathlib import Path
from typing import Any, Optional

INPUT_PER_OUTPUT = 10


class BudgetExhausted(RuntimeError):
    """An explicitly bounded offline experiment reached its total cap."""


class TaskLimitExceeded(RuntimeError):
    """The current attempt spent its own limit."""


class Journal:
    """Append-only JSONL trajectory; never allowed to break the run."""

    def __init__(self, path: Path):
        self.path = path
        self._lock = threading.Lock()
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
        except OSError:
            pass

    def write(self, event: str, **fields: Any) -> None:
        line = json.dumps({"t": round(time.time(), 3), "event": event, **fields}, ensure_ascii=False)
        with self._lock:
            print(line, file=sys.stderr, flush=True)
            try:
                with self.path.open("a", encoding="utf-8") as f:
                    f.write(line + "\n")
            except OSError:
                pass


class Budget:
    """Advisory global estimate and enforceable task caps; the proxy owns the total cutoff."""

    def __init__(self, total: float, journal: Journal, *, enforce_total: bool = False):
        self.total = float(total)
        self.enforce_total = enforce_total  # opt-in for bounded offline experiments only
        self.spent = 0.0
        self.journal = journal
        self.task_id: Optional[str] = None
        self.task_spent = 0.0
        self.task_limit = float("inf")
        self.task_hard_limit = float('inf')
        self._lock = threading.Lock()

    def remaining(self) -> float:
        """Planning estimate only: zero must not stop the competition runner."""
        with self._lock:
            return max(0.0, self.total - self.spent)

    def begin_task(self, task_id: str, limit: float, hard_limit: float | None = None) -> None:
        with self._lock:
            self.task_id, self.task_spent, self.task_limit = task_id, 0.0, float(limit)
            self.task_hard_limit = float(limit if hard_limit is None else hard_limit)
            self.task_limit = min(self.task_limit, self.task_hard_limit)

    def extend_task_limit(self, limit: float) -> None:
        with self._lock:
            self.task_limit = min(self.task_hard_limit, max(self.task_limit, float(limit)))

    def end_task(self) -> float:
        with self._lock:
            spent, self.task_id, self.task_limit = self.task_spent, None, float("inf")
            self.task_hard_limit = float('inf')
            return spent

    def check(self) -> None:
        """Called before every model request."""
        with self._lock:
            if self.enforce_total and self.spent >= self.total:
                raise BudgetExhausted(f"spent {self.spent:.0f} of {self.total:.0f}")
            if self.task_spent >= self.task_limit:
                raise TaskLimitExceeded(f"{self.task_id}: {self.task_spent:.0f} >= {self.task_limit:.0f}")

    def charge(self, model: str, input_tokens: int, output_tokens: int, estimated: bool) -> float:
        cost = input_tokens / INPUT_PER_OUTPUT + output_tokens
        with self._lock:
            self.spent += cost
            self.task_spent += cost
            spent, task_id = self.spent, self.task_id
        self.journal.write(
            "llm_call", task=task_id, model=model, input=input_tokens, output=output_tokens,
            cost=round(cost, 1), spent=round(spent, 1), estimated=estimated,
        )
        return cost
