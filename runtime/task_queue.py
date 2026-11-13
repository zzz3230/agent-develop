"""AGE-12: minimal task order by reward and the measured cost/success of the task type.

Score of a task = reward * p(type) / c(type), where p and c are learned during the run
from the harness's own observable outcomes (no references). Priors are deliberately
neutral and derived only from attempt_policy limits, not fitted to any benchmark.

QUEUE=0 keeps the baseline directory order. RETRY=1 allows at most one extra attempt
per task, only after a limit stop, only when its expected gain per token is not worse
than the best fresh task, and only if the estimated remaining budget covers it.
"""
from __future__ import annotations

import os
import math
import time
from dataclasses import dataclass
from typing import Callable, Iterable, Optional

from runtime.attempt_policy import AttemptLimits, fixed, limits_for_task

PRIOR_SUCCESS = 0.5
PRIOR_WEIGHT = 2.0      # pseudo-attempts behind the success prior
COST_WEIGHT = 1.0       # pseudo-attempts behind the cost prior
SUSPECT_FACTOR = 0.001  # below any honest task, still above a zero-reward one: run last, not never
RETRY_DISCOUNT = 0.3   # a repeat of a failed attempt is assumed much less likely to succeed
LIMIT_STOPS = ('task_cost_limit', 'no_progress_step_limit', 'no_progress_time_limit', 'step limit',
               'task cost limit', 'task time limit')


def queue_enabled() -> bool:
    return os.environ.get('QUEUE', '1') != '0'


def retries_enabled() -> bool:
    return os.environ.get('RETRY', '0') == '1'


def retry_limits(limits: AttemptLimits) -> AttemptLimits:
    """A retry starts at the profile ceiling instead of repeating the same short start."""
    return fixed(limits)


@dataclass
class TypeStats:
    attempts: float = 0.0
    solved: float = 0.0
    cost: float = 0.0


class TaskQueue:
    def __init__(self, tasks: Iterable, enabled: bool = True, retries: bool = False,
                 limits: Callable[[str], AttemptLimits] = limits_for_task, journal=None):
        self.fresh = list(tasks)          # baseline order is the given (directory) order
        self.enabled, self.retries = enabled, retries
        self.limits, self.journal = limits, journal
        self.stats: dict[str, TypeStats] = {}
        self.retry_pool: list = []
        self.retried: set[str] = set()
        self.predictor = None
        self.alpha=float(os.environ.get('SCORE_ALPHA','1'))
        if not math.isfinite(self.alpha) or not 0<=self.alpha<=4:raise ValueError('SCORE_ALPHA must be between 0 and 4')
        self.policy=os.environ.get('QUEUE_POLICY','greedy')
        if self.policy not in ('greedy','knapsack'):raise ValueError('Unknown queue policy')
        # CODING_PRECHECK=1: coding tasks whose visible tests contradict themselves go last.
        self.suspects: dict[str, str] = {}
        if enabled and os.environ.get('CODING_PRECHECK') == '1':
            from runtime.coding_precheck import contradictory_tests
            for t in self.fresh:
                reason = contradictory_tests(t.cwd) if t.type == 'coding' and hasattr(t, 'cwd') else None
                if reason:
                    self.suspects[t.id] = reason
                    self._log('precheck_suspect', task=t.id, reason=reason)
        mode=os.environ.get('PREDICTOR','baseline')
        if enabled and mode != 'baseline':
            if mode not in ('numeric','embedding','structural','strong_embedding','bge_structural','bge_keywords'): raise ValueError('Unknown predictor: '+mode)
            from runtime.predictor import Predictor
            self.predictor=Predictor(self.fresh,mode,os.environ.get('PREDICTOR_DIR','/app/predictors'),journal)

    # --- estimates -------------------------------------------------------
    def _prior_cost(self, kind: str) -> float:
        limits = self.limits(kind)
        return (limits.initial_cost + limits.cost) / 2

    def success(self, kind: str) -> float:
        s = self.stats.get(kind, TypeStats())
        return (s.solved + PRIOR_SUCCESS * PRIOR_WEIGHT) / (s.attempts + PRIOR_WEIGHT)

    def cost(self, kind: str) -> float:
        s = self.stats.get(kind, TypeStats())
        return (s.cost + self._prior_cost(kind) * COST_WEIGHT) / (s.attempts + COST_WEIGHT)

    def score(self, task, retry: bool = False) -> float:
        if task.id in self.suspects:
            return self._score(task, retry) * SUSPECT_FACTOR
        return self._score(task, retry)

    def _score(self, task, retry: bool = False) -> float:
        if self.predictor and not retry:
            p,c=self.predictor.predictions[task.id]
            return (task.reward**self.alpha if task.reward>0 else 0)*p/c
        p = self.success(task.type) * (RETRY_DISCOUNT if retry else 1.0)
        c = self.limits(task.type).cost if retry else self.cost(task.type)
        return (task.reward**self.alpha if task.reward>0 else 0) * p / max(c, 1.0)

    # --- queue -----------------------------------------------------------
    def _best_fresh(self, remaining: Optional[float]):
        if not self.fresh:
            return None
        if not self.enabled:
            return self.fresh[0]
        if self.policy=='knapsack' and remaining is not None and remaining>0:
            from runtime.planning import knapsack
            started=time.monotonic()
            estimates=[self.predictor.predictions[t.id] if self.predictor else (self.success(t.type),self.cost(t.type)) for t in self.fresh]
            indices=knapsack([(t.reward*p,c) for t,(p,c) in zip(self.fresh,estimates)],remaining)
            self._log('knapsack_plan',remaining=remaining,selected=[self.fresh[i].id for i in indices],
                seconds=round(time.monotonic()-started,6))
            if indices:return max((self.fresh[i] for i in indices),key=self.score)
        candidates = self.fresh
        if remaining is not None:
            fitting = [t for t in self.fresh if (self.predictor.predictions[t.id][1] if self.predictor else self.cost(t.type)) <= remaining]
            candidates = fitting or self.fresh
        # Stable: ties keep directory order.
        return max(candidates, key=self.score) # max keeps the first equal-score candidate

    def next(self, remaining: Optional[float] = None):
        """Returns (task, is_retry) or None when nothing is worth running."""
        fresh = self._best_fresh(remaining)
        retry = None
        if self.retries and self.retry_pool:
            affordable = [t for t in self.retry_pool
                          if remaining is None or self.limits(t.type).cost <= remaining]
            if affordable:
                retry = max(affordable, key=lambda t: self.score(t, retry=True))
        if retry is not None and (fresh is None or self.score(retry, True) >= self.score(fresh)):
            self.retry_pool.remove(retry)
            self.retried.add(retry.id)
            self._log('queue_pick', task=retry.id, retry=True, score=self.score(retry, True))
            return retry, True
        if fresh is None:
            return None
        self.fresh.remove(fresh)
        if self.enabled:
            p,c=self.predictor.predictions[fresh.id] if self.predictor else (self.success(fresh.type),self.cost(fresh.type))
            self._log('queue_pick', task=fresh.id, retry=False, score=round(self.score(fresh), 6),
                      p=round(p, 3), c=round(c, 1))
        return fresh, False

    def record(self, task, status: str, cost: float, detail: str = '', retry: bool = False) -> None:
        s = self.stats.setdefault(task.type, TypeStats())
        if not retry:  # type estimates describe first attempts
            s.attempts += 1
            s.cost += cost
            s.solved += status == 'solved'
        if (self.retries and not retry and status == 'failed' and task.id not in self.retried
                and any(reason in (detail or '') for reason in LIMIT_STOPS)):
            self.retry_pool.append(task)

    def _log(self, event: str, **fields) -> None:
        if self.journal is not None:
            self.journal.write(event, **fields)
