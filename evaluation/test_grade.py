"""Grader checks on every reference layout; no model, no Docker (code tests run locally)."""
import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from evaluation.grade import ExactIntMetric, ExactStrMetric, grade

ROOT = Path(__file__).resolve().parents[1]
DIVERSE = ROOT / 'benchmarks' / 'diverse-v1'
FIXTURES = ROOT / 'evaluation' / 'fixtures'


def journal(path: Path, events):
    path.write_text(''.join(json.dumps({'t': i, **e}) + '\n' for i, e in enumerate(events)), encoding='utf-8')


class Metrics(unittest.TestCase):
    def test_exact_int_only_integers(self):
        m = ExactIntMetric()
        self.assertEqual(m.compute(' 389\n', '389'), 1.0)
        self.assertEqual(m.compute('+389', '389'), 1.0)
        for wrong in ('389.0', '389 tokens', '3 89', '', 'IMPOSSIBLE', '390'):
            self.assertEqual(m.compute(wrong, '389'), 0.0, wrong)

    def test_exact_str_strip_and_case_only(self):
        m = ExactStrMetric()
        self.assertEqual(m.compute('  osaka \n', 'Osaka'), 1.0)
        for wrong in ('Osaka.', 'Osaka  City', '"Osaka"', 'Osaka, Japan'):
            self.assertEqual(m.compute(wrong, 'Osaka' if ' ' not in wrong else 'Osaka City'), 0.0, wrong)


@unittest.skipUnless(DIVERSE.is_dir(), 'benchmarks/diverse-v1 not present')
class DiverseLayout(unittest.TestCase):
    def test_references_pass_and_mistakes_fail(self):
        with tempfile.TemporaryDirectory() as temp:
            run = Path(temp) / 'run'
            subprocess.run([sys.executable, str(DIVERSE / 'suite.py'), 'prepare', '--split', 'holdout',
                            '--order-seed', '101', '--out', str(run)], check=True, capture_output=True)
            manifest = json.loads((DIVERSE / 'manifest.json').read_text(encoding='utf-8'))
            rows = {r['id']: r for r in manifest['tasks'] if r['split'] == 'holdout'}
            folders = {e['id']: run / 'tasks' / e['directory']
                       for e in json.loads((run / 'selection.json').read_text())['tasks']}
            for task_id, folder in folders.items():
                ref = DIVERSE / 'references' / task_id
                if rows[task_id]['check'] == 'unittest':
                    shutil.copy2(ref / 'solution.py', folder / 'solution.py')
                    answer = 'DONE'
                else:
                    answer = str(json.loads((ref / 'answer.json').read_text(encoding='utf-8'))['expected'])
                (folder / 'answer.txt').write_text(answer + '\n', encoding='utf-8')
            report = grade(DIVERSE, run / 'tasks')['total']
            solvable = sum(r['solvable'] for r in rows.values())
            self.assertEqual((report['tasks'], report['correct']), (len(rows), solvable))
            self.assertEqual(report['points'], report['possible'])

            code = next(i for i, r in rows.items() if r['check'] == 'unittest')
            (folders[code] / 'test_solution.py').write_text('print("OK")\n', encoding='utf-8')
            number = next(i for i, r in rows.items() if r['check'] == 'exact_int' and r['solvable'])
            (folders[number] / 'answer.txt').write_text('The answer is 5', encoding='utf-8')
            report = grade(DIVERSE, run / 'tasks')
            self.assertEqual(report['total']['correct'], solvable - 2)
            by_id = {r['id']: r for r in report['rows']}
            self.assertIn('edited', by_id[code]['note'])


class FixtureLayout(unittest.TestCase):
    def test_journal_solved_is_not_proof_and_costs_per_task(self):
        with tempfile.TemporaryDirectory() as temp:
            run = Path(temp) / 'tasks'
            ids = ['math_0000', 'search_0005', 'coding_0003', 'control_unknown_rate']
            for task_id in ids:
                shutil.copytree(FIXTURES / 'tasks' / task_id, run / task_id)
                raw = json.loads((run / task_id / 'task.json').read_text(encoding='utf-8'))
                raw.pop('expected', None)                       # agent input has no references
                (run / task_id / 'task.json').write_text(json.dumps(raw), encoding='utf-8')
            (run / 'math_0000' / 'answer.txt').write_text('389\n', encoding='utf-8')
            (run / 'search_0005' / 'answer.txt').write_text('Kyoto\n', encoding='utf-8')
            (run / 'coding_0003' / 'answer.txt').write_text('DONE\n', encoding='utf-8')   # code still buggy
            trajectory = Path(temp) / 'trajectory.jsonl'
            journal(trajectory, [
                {'event': 'attempt_start', 'task': 'math_0000'},
                {'event': 'llm_call', 'task': 'math_0000', 'input': 1000, 'output': 50, 'cost': 150},
                {'event': 'outcome', 'task': 'math_0000', 'status': 'solved'},
                {'event': 'attempt_start', 'task': 'search_0005'},
                {'event': 'llm_call', 'task': 'search_0005', 'input': 2000, 'output': 20, 'cost': 220},
                {'event': 'outcome', 'task': 'search_0005', 'status': 'solved'},
                {'event': 'attempt_start', 'task': 'coding_0003'},
                {'event': 'llm_call', 'task': 'coding_0003', 'input': 3000, 'output': 100, 'cost': 400},
                {'event': 'outcome', 'task': 'coding_0003', 'status': 'solved'},
                {'event': 'llm_call', 'task': None, 'input': 100, 'output': 0, 'cost': 10},
                {'event': 'finish', 'spent': 780, 'seconds': 9, 'stop': 'all tasks handled'},
            ])
            report = grade(FIXTURES / 'tasks', run, trajectory, FIXTURES / 'private_checks')
            rows = {r['id']: r for r in report['rows'] if r['id'] in ids}
            self.assertTrue(rows['math_0000']['correct'])
            self.assertFalse(rows['search_0005']['correct'])
            self.assertFalse(rows['coding_0003']['correct'])
            self.assertFalse(rows['control_unknown_rate'].get('false_claim'))
            self.assertEqual(report['total']['journal_solved_but_wrong'], 2)
            self.assertEqual((rows['search_0005']['cost'], report['spent']), (220, 780))
            self.assertEqual(len(report['rows']), 4)
            self.assertGreater(report['references_not_in_run'], 0)


class BuildSuiteLayout(unittest.TestCase):
    def test_references_pass(self):
        with tempfile.TemporaryDirectory() as temp:
            out = Path(temp) / 'suite'
            subprocess.run([sys.executable, '-m', 'evaluation.build_suite', 'base', '--output', str(out)],
                           cwd=ROOT, check=True, capture_output=True)
            split = out / 'dev'
            run = Path(temp) / 'run'
            shutil.copytree(split / 'input', run)
            manifest = json.loads((split / 'manifest.json').read_text(encoding='utf-8'))
            for row in manifest['tasks']:
                folder = run / row['id']
                if not row['solvable']:
                    continue
                if row['check'] == 'unittest':
                    shutil.copy2(split / 'references' / row['id'] / 'reference_solution.py',
                                 folder / 'workspace' / 'solution.py')
                    answer = 'DONE'
                else:
                    answer = row['expected']
                (folder / 'answer.txt').write_text(f'{answer}\n', encoding='utf-8')
            total = grade(split, run)['total']
            self.assertEqual((total['correct'], total['points'], total['false_claims']),
                             (total['solvable'], total['possible'], 0))


if __name__ == '__main__':
    unittest.main()
