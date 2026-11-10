"""Task-attempt limits, separate from the global budget and M3 scheduling."""
from dataclasses import dataclass


@dataclass(frozen=True)
class AttemptLimits:
    steps: int = 6
    output_tokens: int = 1200
    cost: float = 2500
    seconds: float = 120
    command_seconds: int = 30
    repeated_errors: int = 3


DEFAULTS = {
    'math': AttemptLimits(),
    'data_analysis': AttemptLimits(steps=8, cost=4000, seconds=180),
    'search': AttemptLimits(steps=10, output_tokens=900, cost=3500, seconds=150),
    'coding': AttemptLimits(steps=10, output_tokens=1600, cost=5000, seconds=240),
}


def limits_for_task(task_type: str) -> AttemptLimits:
    return DEFAULTS.get(task_type, AttemptLimits())
