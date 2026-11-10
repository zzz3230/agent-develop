import asyncio
import json
import unittest
from types import SimpleNamespace
from runtime.sql_profile import SqlCompletionRail


class CompletionTests(unittest.TestCase):
    def check(self, command, content, success=True):
        result = []
        ctx = SimpleNamespace(inputs=SimpleNamespace(tool_name='bash',
            tool_args=json.dumps({'command': command}), tool_result=SimpleNamespace(success=success),
            tool_msg=SimpleNamespace(content=content)), request_force_finish=result.append)
        asyncio.run(SqlCompletionRail().after_tool_call(ctx))
        return result

    def test_rendered_stdout_finishes(self):
        self.assertEqual(self.check('python3 -m runtime.sql_tables --query "SELECT 17" --final',
            'Command: sql\nStdout: OJ_SQL_SCALAR_JSON=17\nStderr: (empty)\nExit Code: 0'),
            [{'output':'17','result_type':'answer'}])

    def test_error_and_unrelated_command_do_not_finish(self):
        self.assertEqual(self.check('echo OJ_SQL_SCALAR_JSON=17', 'OJ_SQL_SCALAR_JSON=17'), [])
        self.assertEqual(self.check('python3 -m runtime.sql_tables --query "SELECT bad"',
            'Stdout: (empty)\nStderr: no such column: bad'), [])
        self.assertEqual(self.check('python3 -m runtime.sql_tables --query "SELECT 17"',
            'OJ_SQL_SCALAR_JSON=17'), [])
        self.assertEqual(self.check('python3 -m runtime.sql_tables --query "SELECT 17" --final',
            'OJ_SQL_SCALAR_JSON=17', success=False), [])


if __name__ == '__main__':
    unittest.main()
