"""Unit checks for the opt-in guards against expensive impossible tasks."""
import os
import unittest
from pathlib import Path

from runtime.attempt_policy import limits_for_task
from runtime.attempt_rail import outside_target, question_keys

ROOT = Path('/data/tasks/0001_search/workspace')


class Keys(unittest.TestCase):
    def test_names_ids_and_quotes(self):
        keys = question_keys("Who owned action item AI-27 when Irina Smith left 'Fjord Data' in version 3.0.0?")
        self.assertTrue({'ai-27', 'irina smith', 'fjord data', '3.0.0'} <= keys)

    def test_sentence_starts_are_not_names(self):
        self.assertNotIn('in which', question_keys('In Which year was X born?'))


class Outside(unittest.TestCase):
    def test_refuses_lookups_above_the_task(self):
        for command in ('find / -name "*price*"', 'ls ../..', 'cat ../task.json', 'ls -la; cat /etc/hostname'):
            self.assertIsNotNone(outside_target(command, ROOT), command)

    def test_allows_normal_work(self):
        for command in ("python3 -c \"print(open('sales.csv').read().count('/api/search'))\"",
                        'ls -la', 'cat kb/person_a.md', 'grep -r Osaka kb/', f'ls {ROOT}/kb', 'ls /tmp',
                        "sed -n 's/a/b/p' data.txt", 'python3 test_mylib.py 2>/dev/null'):
            self.assertIsNone(outside_target(command, ROOT), command)


class RateLimit(unittest.TestCase):
    def test_429_is_retried(self):
        from runtime.metered_model import TRANSIENT
        message = ("FrameworkError: model call failed, reason: openAI API async invoke error: RateLimitError: "
                   "Error code: 429 - Слишком много одновременных запросов")
        self.assertIsNotNone(TRANSIENT.search(message))
        self.assertIsNone(TRANSIENT.search('BadRequestError: Error code: 400 - invalid model'))


class Caps(unittest.TestCase):
    def tearDown(self):
        os.environ.pop('TIGHT_CAPS', None)

    def test_tight_caps_only_when_enabled(self):
        self.assertEqual(limits_for_task('search').cost, 3500)
        os.environ['TIGHT_CAPS'] = '1'
        self.assertEqual(limits_for_task('search').cost, 2000)
        self.assertEqual(limits_for_task('data_analysis').cost, 2000)
        self.assertEqual(limits_for_task('math').cost, 1200)
        self.assertEqual(limits_for_task('coding').cost, 6000)
        self.assertLessEqual(limits_for_task('math').initial_cost, 1200)


if __name__ == '__main__':
    unittest.main()
