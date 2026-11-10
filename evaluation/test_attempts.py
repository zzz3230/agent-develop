import asyncio
import json
import os
import tempfile
import time
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from runtime.attempt_policy import AttemptLimits
from runtime.attempt_rail import AttemptRail
from runtime.budget import Budget, Journal, TaskLimitExceeded
from runtime.search_context import search_context
from runtime.tasks import Task
import run_agent


class AttemptTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.budget = Budget(10000, Journal(self.root/'trajectory.jsonl'))

    def tearDown(self):
        self.temp.cleanup()

    def context(self, result, args=None):
        return SimpleNamespace(inputs=SimpleNamespace(tool_name='bash', tool_args=args or {'command':'python3 test.py'},
            tool_result=SimpleNamespace(success=result), tool_msg=SimpleNamespace(content='same error')),
            request_force_finish=self.finished.append)

    async def test_repeated_errors_stop_but_source_progress_resets(self):
        self.finished=[]
        source=self.root/'lib.py'; source.write_text('x=0')
        rail=AttemptRail(self.root,AttemptLimits())
        await rail.after_tool_call(self.context(False))
        await rail.after_tool_call(self.context(False))
        source.write_text('x=1')
        await rail.after_tool_call(self.context(False))
        self.assertEqual(self.finished,[])
        await rail.after_tool_call(self.context(False))
        await rail.after_tool_call(self.context(False))
        self.assertEqual(self.finished[0]['stop_reason'],'repeated_tool_error')

    async def test_commands_use_native_timeout_and_foreground(self):
        self.finished=[]
        ctx=self.context(True, {'command':'python3 test.py','timeout':999,'run_in_background':True})
        await AttemptRail(self.root,AttemptLimits()).before_tool_call(ctx)
        self.assertEqual(ctx.inputs.tool_args['timeout'],30)
        self.assertFalse(ctx.inputs.tool_args['run_in_background'])
        ctx.inputs.tool_args=json.dumps({'command':'python3 test.py','timeout':999})
        await AttemptRail(self.root,AttemptLimits()).before_tool_call(ctx)
        self.assertIsInstance(ctx.inputs.tool_args,str)
        self.assertEqual(json.loads(ctx.inputs.tool_args)['timeout'],30)

    async def invoke_fake(self, output, kind='math', check='exact_int', failure=None):
        task=Task('case',kind,'Run `python3 test_lib.py`.',1,self.root,check)
        class Agent:
            async def register_rail(self, rail): pass
            async def invoke(inner, query):
                if failure:
                    (self.root/'test_lib.py').write_text('changed')
                    raise failure
                return {'output':output}
        return await run_agent.attempt(task,self.budget,None,lambda *a,**k:Agent())

    async def test_short_answers_and_internal_limit_message(self):
        self.assertEqual(await self.invoke_fake('158'),('solved','158'))
        self.assertEqual(await self.invoke_fake('IMPOSSIBLE'),('impossible',''))
        self.assertEqual(await self.invoke_fake('Max iterations reached without completion'),('failed','step limit'))
        self.assertEqual(await self.invoke_fake('result: 158'),('failed','invalid integer answer'))

    async def test_tests_restored_on_timeout(self):
        test=self.root/'test_lib.py'; test.write_text('original')
        status,detail=await self.invoke_fake('',kind='coding',failure=asyncio.TimeoutError())
        self.assertEqual((status,detail),('failed','agent edited the tests'))
        self.assertEqual(test.read_text(),'original')

    async def test_done_requires_passing_tests(self):
        (self.root/'test_lib.py').write_text('import unittest\nclass T(unittest.TestCase):\n def test_ok(self): self.assertEqual(2+2,4)\nif __name__=="__main__": unittest.main()\n')
        self.assertEqual(await self.invoke_fake('DONE',kind='coding'),('solved','DONE'))

    async def test_verified_code_survives_model_failure(self):
        (self.root/'test_lib.py').write_text('import unittest\nclass T(unittest.TestCase):\n def test_ok(self): self.assertTrue(True)\nif __name__=="__main__": unittest.main()\n')
        class Agent:
            async def register_rail(self,rail): pass
            async def invoke(self,query): raise RuntimeError('proxy temporarily unavailable')
        task=Task('coding','coding','Run `python3 test_lib.py`.',1,self.root,'unittest')
        self.assertEqual(await run_agent.attempt(task,self.budget,None,lambda *a,**k:Agent()),('solved','DONE'))

    async def test_task_limits_do_not_trigger_global_api_error_stop(self):
        tasks=[]
        for i in range(5):
            d=self.root/str(i); d.mkdir()
            tasks.append(Task(str(i),'math','',1,d,'exact_int'))
        async def invoke(task,*a,**k):
            if task.id!='4': raise TaskLimitExceeded('task cap')
            return 'solved','42'
        with patch.dict(os.environ,{'LLM_BASE_URL':'http://unused','LLM_API_KEY':'unused'}), patch.object(run_agent,'attempt',invoke):
            stop=await run_agent.run(tasks,self.budget,self.budget.journal,time.monotonic()+60)
        self.assertEqual(stop,'all tasks handled')
        self.assertEqual((tasks[-1].dir/'answer.txt').read_text().strip(),'42')
        self.assertIsNone(self.budget.task_id)

    async def test_search_context_excludes_references_and_is_bounded(self):
        (self.root/'task.json').write_text('{"expected":"secret"}')
        (self.root/'answer.txt').write_text('secret')
        (self.root/'person.md').write_text('Researcher A is at Company B.')
        context=search_context(self.root,'Where is Researcher A?',limit=200)
        self.assertIn('person.md',context)
        self.assertNotIn('secret',context)
        self.assertLessEqual(len(context),500)


if __name__=='__main__': unittest.main()
