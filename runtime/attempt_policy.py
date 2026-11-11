"""Task-attempt limits, separate from the global budget and M3 scheduling."""
import os
from dataclasses import dataclass, replace


@dataclass(frozen=True)
class AttemptLimits:
    steps: int = 6
    output_tokens: int = 1200
    cost: float = 2500
    seconds: float = 120
    command_seconds: int = 30
    repeated_errors: int = 3
    initial_steps: int = 3
    initial_cost: float = 700
    initial_seconds: float = 45
    step_increment: int = 2
    cost_increment: float = 900
    time_increment: float = 45
    max_extensions: int = 2


DEFAULTS = {
    'math': AttemptLimits(),
    'data_analysis': AttemptLimits(steps=12, cost=4500, seconds=180, initial_cost=900,
                                  step_increment=3, cost_increment=1200, max_extensions=3),
    'search': AttemptLimits(steps=13, output_tokens=900, cost=3500, seconds=150,
                           initial_steps=4, initial_cost=800, step_increment=3, max_extensions=3),
    'coding': AttemptLimits(steps=14, output_tokens=1600, cost=6000, seconds=240,
                           initial_steps=5, initial_cost=1500, initial_seconds=60,
                           step_increment=3, cost_increment=1500, time_increment=60, max_extensions=3),
}


def fixed(limits: AttemptLimits) -> AttemptLimits:
    """Whole ceiling from the first step, no progress-based extensions."""
    return replace(limits, initial_steps=limits.steps, initial_cost=limits.cost,
                   initial_seconds=limits.seconds, max_extensions=0)


def limits_for_task(task_type: str) -> AttemptLimits:
    limits = DEFAULTS.get(task_type, AttemptLimits())
    return limits if os.environ.get('ADAPTIVE_LIMITS', '1') == '1' else fixed(limits)
