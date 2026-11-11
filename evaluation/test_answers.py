"""Answer extraction and the bash path check fix (no model calls)."""
import os
import tempfile
import time
import unittest
from pathlib import Path

import run_agent
from runtime import oj_agent  # noqa: F401  (installs the path check fix)
from openjiuwen.core.sys_operation.local.shell_operation import ShellOperation


class AnswerTest(unittest.TestCase):
    def test_final_line(self):
        self.assertEqual(run_agent.final_line('Done.\nThe version is **3.0.0** (4.3.1 withdrawn).'), '3.0.0')
        self.assertEqual(run_agent.final_line('`42`'), '42')
        self.assertEqual(run_agent.final_line('Hana Ivanova'), 'Hana Ivanova')

    def test_written_answer_only_from_this_attempt(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'answer.txt'
            path.write_text('3.0.0\n')
            self.assertEqual(run_agent.written_answer(path, time.time()), '3.0.0')
            os.utime(path, (time.time() - 100, time.time() - 100))
            self.assertEqual(run_agent.written_answer(path, time.time()), '')
            path.write_text('a\nb\n')
            self.assertEqual(run_agent.written_answer(path, time.time()), '')

    def test_path_check_ignores_values_that_cannot_be_files(self):
        found = lambda cmd: [str(p) for p in ShellOperation._extract_abs_paths(None, cmd)]
        self.assertEqual(found("python3 -c \"e=='/api/search'\""), [])
        self.assertEqual(found('cat /etc/passwd'), ['/etc/passwd'])
        self.assertEqual(found('echo x > /tmp/x'), ['/tmp/x'])


if __name__ == '__main__':
    unittest.main()
