"""Exercise native OJ stopping against a local deterministic mock API."""
import asyncio
import json
import os
import tempfile
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from runtime.budget import Budget, Journal, TaskLimitExceeded, BudgetExhausted
from runtime.tasks import Task
from runtime.attempt_policy import AttemptLimits


class API(BaseHTTPRequestHandler):
    calls=0
    mode='errors'
    progress_calls=0
    def log_message(self,*args): pass
    def do_POST(self):
        data=json.loads(self.rfile.read(int(self.headers['Content-Length'])))
        API.calls+=1
        message={'role':'assistant','content':None,'tool_calls':[{'id':f'call-{API.calls}', 'type':'function',
            'function':{'name':'bash','arguments':json.dumps({'command':'python3 -c "raise ValueError(\'stuck\')"'})}}]}
        if API.mode=='progress':
            API.progress_calls+=1
            if API.progress_calls<=5:
                message['tool_calls'][0]['function']['arguments']=json.dumps({'command':f'python3 -c "print({API.progress_calls})"'})
            else:
                message={'role':'assistant','content':'42'}
        result={'id':str(API.calls),'object':'chat.completion','created':int(time.time()),'model':data['model'],
            'choices':[{'index':0,'message':message,'finish_reason':'tool_calls' if message.get('tool_calls') else 'stop'}],
            'usage':{'prompt_tokens':100,'completion_tokens':50,'total_tokens':150}}
        encoded=json.dumps(result).encode()
        self.send_response(200); self.send_header('Content-Type','application/json')
        self.send_header('Content-Length',str(len(encoded))); self.end_headers(); self.wfile.write(encoded)


async def main():
    from runtime.oj_agent import Connection,react_agent
    from run_agent import attempt
    server=ThreadingHTTPServer(('127.0.0.1',0),API)
    threading.Thread(target=server.serve_forever,daemon=True).start()
    try:
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp)
            budget=Budget(1,Journal(root/'usage.jsonl')); budget.begin_task('loop',3000)
            status,detail=await attempt(Task('loop','math','Try the computation.',1,root,'exact_int'),budget,
                Connection(f'http://127.0.0.1:{server.server_port}/v1','mock'),react_agent,
                AttemptLimits(steps=10,seconds=30))
            assert (status,detail)==('failed','repeated_tool_error'),(status,detail)
            assert API.calls==3,API.calls
            print('PASS: stock ReActAgent stopped after 3 identical failed tool calls')
            print('PASS: local total estimate exceeded without stopping the model')
            API.mode='progress'
            budget=Budget(1,Journal(root/'progress.jsonl'))
            budget.begin_task('progress',100,hard_limit=600)
            outcome=await attempt(Task('progress','math','Compute the answer.',1,root,'exact_int'),budget,
                Connection(f'http://127.0.0.1:{server.server_port}/v1','mock'),react_agent,
                AttemptLimits(steps=8,cost=600,initial_steps=2,initial_cost=100,
                              step_increment=2,cost_increment=150,max_extensions=3,seconds=30))
            assert outcome==('solved','42'),outcome
            assert API.progress_calls==6,API.progress_calls
            extensions=[json.loads(line) for line in (root/'progress.jsonl').read_text().splitlines() if 'attempt_extended' in line]
            assert len(extensions)==2,extensions
            print('PASS: native progress extended the same session twice and completed in 6 calls')
            API.mode='errors'
            for total,task_cap,expected in [(10000,60,TaskLimitExceeded),(60,3000,BudgetExhausted)]:
                budget=Budget(total,Journal(root/f'budget-{total}.jsonl'),enforce_total=expected is BudgetExhausted)
                budget.begin_task('cap',task_cap)
                try:
                    outcome=await attempt(Task('cap','math','Try the computation.',1,root,'exact_int'),budget,
                        Connection(f'http://127.0.0.1:{server.server_port}/v1','mock'),react_agent,
                        AttemptLimits(steps=10,seconds=30))
                except Exception as exc:
                    chain=[]; current=exc
                    while current is not None and current not in chain:
                        chain.append(current); current=current.__cause__ or current.__context__
                    assert any(isinstance(e,expected) for e in chain),[(type(e).__name__,str(e)) for e in chain]
                    print('PASS: native budget stop',[(type(e).__name__) for e in chain])
                else:
                    assert expected is TaskLimitExceeded and outcome==('failed','task_cost_limit'),outcome
                    print('PASS: native task limit finishes gracefully')
    finally:
        server.shutdown()


if __name__=='__main__':
    os.chdir(tempfile.mkdtemp(prefix='oj-stop-check-'))
    asyncio.run(main())
