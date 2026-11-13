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


class GapRules(unittest.TestCase):
    def tearDown(self):
        os.environ.pop('IMPOSSIBLE_RULES', None)

    def test_rules_only_when_enabled(self):
        from runtime.profiles import BASELINE_SYSTEM, CODING_GAP_RULES, GAP_RULES, system_for_task
        self.assertEqual(system_for_task('search'), BASELINE_SYSTEM)
        os.environ['IMPOSSIBLE_RULES'] = '1'
        for kind in ('math', 'data_analysis', 'search'):
            self.assertTrue(system_for_task(kind).endswith(GAP_RULES), kind)
        self.assertTrue(system_for_task('coding').endswith(CODING_GAP_RULES))
        self.assertNotIn(GAP_RULES, system_for_task('coding'))


class GapSignals(unittest.TestCase):
    @staticmethod
    def out(stdout, code=0, stderr='(empty)'):
        return f'Command: x\nStdout: {stdout}\n\nStderr: {stderr}\nExit Code: {code}'

    def test_signs_of_missing_data(self):
        from runtime.attempt_rail import gap_signal
        seen = set()
        self.assertEqual(gap_signal('grep -ri price .', self.out('(empty)', 1), seen), 'nothing_found')
        self.assertEqual(gap_signal('python3 a.py', self.out('(empty)', 1, "KeyError: 'GBP'"), seen), 'missing')
        self.assertEqual(gap_signal('stat -c %y kb/*', self.out('kb/a.md 2026'), seen), 'hidden_data_hunt')
        self.assertEqual(gap_signal('find . -name ".*" -type f', self.out('(empty)'), seen), 'hidden_data_hunt')
        self.assertEqual(gap_signal('cat x', "echo 'Refused: / is outside'", seen), 'outside')

    def test_normal_work_is_quiet(self):
        from runtime.attempt_rail import gap_signal
        seen = set()
        self.assertIsNone(gap_signal('cat kb/a.md', self.out('Headquarters: Osaka'), seen))
        self.assertIsNone(gap_signal('python3 -c "print(1)"', self.out('(empty)'), seen))
        self.assertIsNone(gap_signal('echo Osaka > answer.txt', self.out('(empty)'), seen))
        self.assertIsNone(gap_signal('python3 -c "print(0)"', self.out('0'), seen))
        self.assertEqual(gap_signal('cat kb/a.md', self.out('Headquarters: Osaka'), seen), 'repeated_output')

    def test_glued_separator(self):
        from runtime.attempt_rail import _GLUED
        self.assertEqual(_GLUED.sub(r'\1 ', 'ls; head a.csv'), 'ls ; head a.csv')
        self.assertEqual(_GLUED.sub(r'\1 ', 'ls -la; cat x'), 'ls -la; cat x')


class TestHack(unittest.TestCase):
    def test_pattern(self):
        from runtime.attempt_rail import _TEST_HACK
        self.assertTrue(_TEST_HACK.search("cat > lib.py << 'EOF'\nclass _Code(str):\n    pass\nEOF"))
        self.assertTrue(_TEST_HACK.search("python3 -c 'import builtins; builtins.int = str'"))
        self.assertFalse(_TEST_HACK.search("cat > lib.py << 'EOF'\ndef code(n):\n    return '%03d' % n\nEOF"))
        self.assertFalse(_TEST_HACK.search("python3 test_mylib.py -v"))


class Precheck(unittest.TestCase):
    def setUp(self):
        import tempfile
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        (self.root / 'kb').mkdir()
        (self.root / 'kb' / 'person_sergei_petrov.md').write_text('# Sergei Petrov\n\nBorn: 1981\n')
        (self.root / 'kb' / 'person_alice_sato.md').write_text('# Alice Sato\n\nBorn: 1991\n')
        (self.root / 'kb' / 'person_alice_sato_2.md').write_text('# Alice Sato\n\nBorn: 1998\n')
        (self.root / 'sales.csv').write_text('order_id,units\n1,2\n')

    def tearDown(self):
        self.tmp.cleanup()

    def test_facts(self):
        from runtime.precheck import precheck
        self.assertIn("closest name in the files is 'Sergei Petrov'", precheck(self.root, 'When was Sergie Petrov born?', 'search'))
        self.assertIn("'Zora Vance' does not occur", precheck(self.root, 'When was Zora Vance born?', 'search'))
        self.assertIn("'Alice Sato' is the title of 2 files", precheck(self.root, 'When was Alice Sato born?', 'search'))
        self.assertIn('closest existing file is sales.csv', precheck(self.root, 'Sum units in salse.csv.', 'data_analysis'))
        self.assertIn('existing directories: kb/', precheck(self.root, 'Use kn/ to find it.', 'search'))

    def test_csv_facts(self):
        from runtime.precheck import precheck
        (self.root / 'rates.csv').write_text('currency,usd\nEUR,1.1\nUSD,1\n')
        (self.root / 'orders.csv').write_text('order_id,currency,cents\n1,EUR,5\n2,GBP,7\n2,USD,1\n3,USD,4\n')
        note = precheck(self.root, 'Convert orders.csv with rates.csv. What is order 2?', 'data_analysis')
        self.assertIn('currency values of orders.csv absent from rates.csv: GBP (1 rows)', note)
        self.assertIn('order_id 2 occurs in 2 rows', note)

    def test_quiet_when_everything_exists(self):
        from runtime.precheck import precheck
        self.assertEqual(precheck(self.root, 'In kb/, when was Sergei Petrov born? Write answer.txt.', 'search'), '')
        self.assertEqual(precheck(self.root, 'Sum units in sales.csv. Ignore task.json.', 'data_analysis'), '')
        self.assertEqual(precheck(self.root, 'Fix mylib.py so that test_mylib.py passes.', 'coding'), '')


if __name__ == '__main__':
    unittest.main()
