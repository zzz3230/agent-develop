"""run_image/select_release logic with the fake docker CLI (no sandbox limits are tested here)."""
import json
import os
import shutil
import stat
import sys
import tempfile
import unittest
from pathlib import Path

from evaluation import run_image, select_release

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / 'evaluation' / 'fixtures'


@unittest.skipIf(os.name == "nt", "fake docker shim needs a POSIX shell")
class RunImageTest(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp, True)
        fake = self.tmp / 'bin' / 'docker'
        fake.parent.mkdir()
        fake.write_text(f'#!/bin/sh\nexec {sys.executable} {ROOT / "evaluation" / "fake_docker.py"} "$@"\n')
        fake.chmod(fake.stat().st_mode | stat.S_IEXEC)
        self.path = os.environ['PATH']
        os.environ['PATH'] = f'{fake.parent}:{self.path}'
        os.environ['FAKE_DOCKER_STATE'] = str(self.tmp / 'state')
        self.tasks = self.tmp / 'tasks'
        for name in ('math_0000', 'math_0004'):
            shutil.copytree(FIXTURES / 'tasks' / name, self.tasks / name)

    def tearDown(self):
        os.environ['PATH'] = self.path

    def test_refuses_references_in_input(self):
        (self.tasks / 'math_0000' / 'answer.json').write_text('{}')
        with self.assertRaises(ValueError):
            run_image.copy_tasks(self.tasks, self.tmp / 'copy')

    def test_mock_run_grades_and_selects(self):
        with run_image.Mock('hack:test') as mock:
            info = run_image.run('hack:test', self.tasks, self.tmp / 'run', mock=mock, references=FIXTURES / 'tasks',
                                 with_probe=False, quiet=True)
        for task_json in (self.tmp / 'run' / 'tasks').glob('*/task.json'):
            self.assertNotIn('expected', json.loads(task_json.read_text()))
        self.assertEqual(info['exit_code'], 0)
        self.assertEqual(info['finish']['stop'], 'all tasks handled')
        self.assertEqual(info['total']['correct'], 1)  # mock always answers 389 = math_0000
        self.assertNotIn('LLM_API_KEY=mock', (self.tmp / 'run' / 'run.json').read_text())
        rows = select_release.choose({'a': [select_release.load(self.tmp / 'run')]})
        self.assertEqual(rows[0]['points'], 5)


if __name__ == '__main__':
    unittest.main()
