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
    def log_message(self,*args): pass
    def do_POST(self):
        data=json.loads(self.rfile.read(int(self.headers['Content-Length'])))
        API.calls+=1
        message={'role':'assistant','content':None,'tool_calls':[{'id':f'call-{API.calls}', 'type':'function',
            'function':{'name':'bash','arguments':json.dumps({'command':'python3 -c "raise ValueError(\'stuck\')"'})}}]}
        result={'id':str(API.calls),'object':'chat.completion','created':int(time.time()),'model':data['model'],
            'choices':[{'index':0,'message':message,'finish_reason':'tool_calls'}],
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
            budget=Budget(10000,Journal(root/'usage.jsonl')); budget.begin_task('loop',3000)
            status,detail=await attempt(Task('loop','math','Try the computation.',1,root,'exact_int'),budget,
                Connection(f'http://127.0.0.1:{server.server_port}/v1','mock'),react_agent,
                AttemptLimits(steps=10,seconds=30))
            assert (status,detail)==('failed','repeated_tool_error'),(status,detail)
            assert API.calls==3,API.calls
            print('PASS: stock ReActAgent stopped after 3 identical failed tool calls')
            for total,task_cap,expected in [(10000,60,TaskLimitExceeded),(60,3000,BudgetExhausted)]:
                budget=Budget(total,Journal(root/f'budget-{total}.jsonl'))
                budget.begin_task('cap',task_cap)
                try:
                    await attempt(Task('cap','math','Try the computation.',1,root,'exact_int'),budget,
                        Connection(f'http://127.0.0.1:{server.server_port}/v1','mock'),react_agent,
                        AttemptLimits(steps=10,seconds=30))
                except Exception as exc:
                    chain=[]; current=exc
                    while current is not None and current not in chain:
                        chain.append(current); current=current.__cause__ or current.__context__
                    assert any(isinstance(e,expected) for e in chain),[(type(e).__name__,str(e)) for e in chain]
                    print('PASS: native budget stop',[(type(e).__name__) for e in chain])
                else:
                    raise AssertionError('Expected budget exception')
    finally:
        server.shutdown()


if __name__=='__main__':
    os.chdir(tempfile.mkdtemp(prefix='oj-stop-check-'))
    asyncio.run(main())
