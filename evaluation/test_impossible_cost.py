"""Unit checks for the opt-in measures against spending on impossible tasks:
PROGRESS_STRICT, CODING_PRECHECK and IMPOSSIBLE_PROMPT (all off by default)."""
import os
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from runtime.attempt_policy import limits_for_task
from runtime.attempt_rail import AttemptRail, lookup_only
from runtime.coding_precheck import _contradiction, contradictory_tests
from runtime.profiles import system_for_task
from runtime.task_queue import TaskQueue

HEAD = 'import unittest\nimport mylib as m\nfrom mylib import code\n\nclass T(unittest.TestCase):\n'


def tests(*lines):
    return HEAD + ''.join(f'    def test_{i}(self):\n        {line}\n' for i, line in enumerate(lines))


def shell(stdout, code=0):
    return f'Command: x\nStdout: {stdout}\n\nStderr: (empty)\nExit Code: {code}'


class Flags(unittest.TestCase):
    names = ('PROGRESS_STRICT', 'CODING_PRECHECK', 'IMPOSSIBLE_PROMPT')

    def setUp(self):
        for name in self.names:
            os.environ.pop(name, None)

    tearDown = setUp


class Contradictions(Flags):
    def test_found(self):
        for body in (
            tests('self.assertEqual(m.add_tax(100), 120)', 'self.assertEqual(m.add_tax(100), 121)'),
            tests('self.assertIsInstance(m.code(7), int)', "self.assertEqual(m.code(7), '007')"),
            tests('self.assertEqual(3, code(1))', 'self.assertNotEqual(code(1), 3)'),
            tests("self.assertEqual(m.f('a', k=1), [1])", "self.assertEqual(m.f('a', k=1), [2])"),
        ):
            self.assertIsNotNone(_contradiction(body), body)

    def test_compatible_tests_are_left_alone(self):
        for body in (
            tests('self.assertEqual(m.f(1), 1)', 'self.assertEqual(m.f(1), 1.0)'),          # equal values
            tests('self.assertEqual(m.f(7), 7.0)', 'self.assertIsInstance(m.f(7), int)'),   # 7 == 7.0
            tests('self.assertEqual(m.f(1), True)', 'self.assertIsInstance(m.f(1), int)'),  # bool is an int
            tests('self.assertEqual(m.f(1), 2)', 'self.assertEqual(m.f(2), 3)'),            # different calls
            tests('self.assertEqual(m.next_id(), 1)', 'self.assertEqual(m.next_id(), 2)'),  # stateful, no args
            tests('c = m.Counter()', 'self.assertEqual(c.add(1), 1)', 'self.assertEqual(c.add(1), 2)'),
            tests('self.assertEqual(m.f(x), 1)', 'self.assertEqual(m.f(x), 2)'),            # variable argument
            tests('self.assertEqual(m.f(1), 2)', 'self.assertNotEqual(m.f(1), 3)'),
            'def broken(:\n',
        ):
            self.assertIsNone(_contradiction(body), body)

    def test_directory_scan_and_queue_order(self):
        with tempfile.TemporaryDirectory() as tmp:
            bad, good = Path(tmp, 'bad'), Path(tmp, 'good')
            for directory, second in ((bad, 121), (good, 120)):
                directory.mkdir()
                (directory / 'test_mylib.py').write_text(
                    tests('self.assertEqual(m.add_tax(100), 120)', f'self.assertEqual(m.add_tax(100), {second})'))
            self.assertIn('add_tax(100)', contradictory_tests(bad))
            self.assertIsNone(contradictory_tests(good))
            self.assertIsNone(contradictory_tests(Path(tmp, 'absent')))

            def queue():
                os.environ['PREDICTOR'] = 'baseline'   # stub tasks have no text for the embedding predictor
                return TaskQueue([SimpleNamespace(id='bad', type='coding', reward=10, cwd=bad),
                                  SimpleNamespace(id='good', type='coding', reward=1, cwd=good),
                                  SimpleNamespace(id='math', type='math', reward=1, cwd=good)])

            def order(q):
                picked = []
                while (pick := q.next(1000)) is not None:
                    picked.append(pick[0].id)
                    q.record(pick[0], 'solved', 100)
                return picked

            default = order(queue())
            self.assertLess(default.index('bad'), default.index('good'))   # off: the higher reward first
            os.environ['CODING_PRECHECK'] = '1'
            self.assertEqual(order(queue())[-1], 'bad')             # last, but still run


class Progress(Flags):
    def rail(self, kind):
        return AttemptRail(Path(tempfile.gettempdir()), limits_for_task(kind), task_type=kind)

    def progress(self, kind, calls):
        rail = self.rail(kind)
        for command, text in calls:
            rail.observe_progress(text, {'command': command}, True)
        return rail.fresh_progress

    def test_lookup_only(self):
        for command in ('ls -la', 'cat t.csv', 'head -5 a.csv; echo ---; head -5 b.csv', 'ls -la; find . -name x'):
            self.assertTrue(lookup_only(command), command)
        for command in ('python3 -c "print(1)"', 'cat t.csv | awk -F, \'{s+=$5} END {print s}\'', 'ls; python3 a.py'):
            self.assertFalse(lookup_only(command), command)

    def test_listings_and_repeats_are_not_progress_when_strict(self):
        listing = [('ls -la', shell('total 4\n-rwx 1 root root 876 Nov 12 15:48 t.csv')),
                   ('cat t.csv', shell('id,units\n1,20\n2,26'))]
        twice = [('python3 -c "print(85)"', shell('85')), ('python3 -c "print(\'sum\', 85)"', shell('sum 85'))]
        missing = [('python3 -c "print(3)"; head r.csv', shell('3\nhead: r.csv: No such file or directory'))]
        self.assertTrue(self.progress('data_analysis', listing))    # the old behaviour, kept by default
        os.environ['PROGRESS_STRICT'] = '1'
        self.assertEqual(self.progress('data_analysis', listing), {'first_look'})   # once
        rail = self.rail('data_analysis')
        rail.extensions = 1
        for command, text in listing:
            rail.observe_progress(text, {'command': command}, True)
        self.assertEqual(rail.fresh_progress, set())                # looking again buys nothing
        self.assertEqual(self.progress('data_analysis', missing), set())
        rail = self.rail('data_analysis')
        rail.observe_progress(twice[0][1], {'command': twice[0][0]}, True)
        self.assertEqual(rail.fresh_progress, {'computed_scalar'})  # a first computed number still counts
        rail.fresh_progress.clear()
        rail.observe_progress(twice[1][1], {'command': twice[1][0]}, True)
        self.assertEqual(rail.fresh_progress, set())
        self.assertTrue(self.progress('data_analysis', [('python3 a.py', shell('rows matched: 12\n340'))]))

    def test_green_tests_extend_only_when_not_strict(self):
        green = [('python3 test_mylib.py', shell('Ran 2 tests in 0.000s\n\nOK'))]
        self.assertEqual(self.progress('coding', green), {'tests_passed'})
        os.environ['PROGRESS_STRICT'] = '1'
        self.assertEqual(self.progress('coding', green), set())


class Prompt(Flags):
    def test_default_prompt_is_unchanged_and_flag_adds_grounds(self):
        before = {kind: system_for_task(kind) for kind in ('math', 'data_analysis', 'search', 'coding')}
        os.environ['IMPOSSIBLE_PROMPT'] = '1'
        for kind, text in before.items():
            extended = system_for_task(kind)
            self.assertTrue(extended.startswith(text))
            self.assertIn('IMPOSSIBLE', extended[len(text):])
            self.assertLess(len(extended) - len(text), 600)   # about 100 tokens, 10 per model call


if __name__ == '__main__':
    unittest.main()
