import unittest
import os
from types import SimpleNamespace

from runtime.attempt_policy import AttemptLimits
from runtime.task_queue import TaskQueue, retry_limits


def task(i, kind, reward):
    return SimpleNamespace(id=i, type=kind, reward=reward)


class TaskQueueTests(unittest.TestCase):
    def setUp(self):
        self._predictor = os.environ.get('PREDICTOR')
        os.environ['PREDICTOR'] = 'baseline'

    def tearDown(self):
        if self._predictor is None:
            os.environ.pop('PREDICTOR', None)
        else:
            os.environ['PREDICTOR'] = self._predictor

    def drain(self, queue, outcomes=None, remaining=None):
        order = []
        while (pick := queue.next(remaining)) is not None:
            t, retry = pick
            order.append((t.id, retry))
            status, cost, detail = (outcomes or {}).get(t.id, ('solved', 100, ''))
            queue.record(t, status, cost, detail, retry)
        return order

    def test_disabled_keeps_directory_order(self):
        tasks = [task('a', 'coding', 1), task('b', 'math', 10), task('c', 'search', 5)]
        self.assertEqual(self.drain(TaskQueue(tasks, enabled=False)),
                         [('a', False), ('b', False), ('c', False)])

    def test_reward_and_type_cost_order(self):
        tasks = [task('cheap_low', 'math', 2), task('code_high', 'coding', 6), task('math_high', 'math', 9)]
        order = [i for i, _ in self.drain(TaskQueue(tasks))]
        self.assertEqual(order[0], 'math_high')   # 9 / 1600 beats 6 / 3750

    def test_measured_type_failures_push_type_back(self):
        tasks = [task('s1', 'search', 9), task('s2', 'search', 9), task('m1', 'math', 4)]
        outcomes = {'s1': ('failed', 3500, 'task_cost_limit')}
        order = [i for i, _ in self.drain(TaskQueue(tasks), outcomes)]
        self.assertEqual(order, ['s1', 'm1', 's2'])

    def test_retry_only_after_limit_stop_and_when_affordable(self):
        tasks = [task('m1', 'math', 10), task('m2', 'math', 5)]
        outcomes = {'m1': ('failed', 700, 'no_progress_step_limit'), 'm2': ('impossible', 300, '')}
        self.assertEqual(self.drain(TaskQueue(tasks, retries=True), outcomes),
                         [('m1', False), ('m2', False), ('m1', True)])
        queue = TaskQueue([task('m1', 'math', 10)], retries=True)
        self.drain(queue, outcomes, remaining=1000)        # ceiling 2500 does not fit
        self.assertNotIn('m1', queue.retried)
        queue = TaskQueue([task('x', 'math', 10)], retries=True)
        self.drain(queue, {'x': ('failed', 10, 'invalid integer answer')})
        self.assertEqual(queue.retried, set())          # not a limit stop: no retry

    def test_remaining_budget_prefers_types_that_fit(self):
        tasks = [task('code', 'coding', 10), task('math', 'math', 1)]
        order = [i for i, _ in self.drain(TaskQueue(tasks), remaining=2000)]
        self.assertEqual(order[0], 'math')

    def test_retry_limits_start_at_ceiling(self):
        limits = retry_limits(AttemptLimits())
        self.assertEqual((limits.initial_cost, limits.initial_steps, limits.max_extensions),
                         (limits.cost, limits.steps, 0))

    def test_switches_for_prompt_and_limits(self):
        import os
        from unittest import mock
        from runtime.attempt_policy import limits_for_task
        from runtime.profiles import BASELINE_SYSTEM, ECONOMY_SYSTEM, system_for_task
        self.assertEqual(system_for_task('coding'), ECONOMY_SYSTEM)
        self.assertEqual(limits_for_task('math').max_extensions, 2)
        with mock.patch.dict(os.environ, {'PROMPT_ECONOMY': '0', 'ADAPTIVE_LIMITS': '0'}):
            self.assertEqual(system_for_task('coding'), BASELINE_SYSTEM)
            limits = limits_for_task('math')
            self.assertEqual((limits.initial_cost, limits.max_extensions), (limits.cost, 0))


if __name__ == '__main__':
    unittest.main()
