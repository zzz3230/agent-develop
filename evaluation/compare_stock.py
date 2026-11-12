"""Reference-free comparison of native OJ ReActAgent and the production agent."""
from __future__ import annotations
import argparse
import asyncio
import json
import os
import shutil
import sys
import tempfile
import time
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

STOCK_STEPS = 100
STOCK_OUTPUT_TOKENS = 8192
STOCK_TASK_SECONDS = 600


def stock_agent(budget, connection, model, cwd, *, max_steps=STOCK_STEPS, max_output=STOCK_OUTPUT_TOKENS):
    from openjiuwen.core.foundation.llm import ModelRequestConfig
    from openjiuwen.core.runner import Runner
    from openjiuwen.core.single_agent import AgentCard, ReActAgent, ReActAgentConfig
    from openjiuwen.core.sys_operation import LocalWorkConfig, OperationMode, SysOperationCard
    from openjiuwen.core.sys_operation.cwd import set_cwd
    from runtime.metered_model import MeteredModel
    from runtime.oj_agent import STOCK_TOOLS, SHELL_ALLOWLIST
    client = connection.client()
    request = ModelRequestConfig(model=model, temperature=0.0, max_tokens=max_output)
    operation_id = 'stock-' + uuid.uuid4().hex
    Runner.resource_mgr.add_sys_operation(SysOperationCard(id=operation_id, mode=OperationMode.LOCAL,
        work_config=LocalWorkConfig(sandbox_root=[cwd], restrict_to_sandbox=True, shell_allowlist=SHELL_ALLOWLIST)))
    operation = Runner.resource_mgr.get_sys_operation(operation_id)
    set_cwd(cwd)
    agent = ReActAgent(AgentCard(name='solver', description='solver', id='stock-'+uuid.uuid4().hex))
    # Keep the native prompt and full tool cards; expose caps for controlled comparisons.
    agent.configure(ReActAgentConfig(model_name=model, model_provider='OpenAI', api_key=connection.api_key,
        api_base=connection.base_url, model_client_config=client, model_config_obj=request,
        max_iterations=max_steps))
    agent.set_llm(MeteredModel(client, request, budget))
    for cls in STOCK_TOOLS.values():
        tool = cls(operation, language='en', agent_id=agent.card.id)
        Runner.resource_mgr.add_tool(tool)
        agent.ability_manager.add(tool.card)
    return agent


async def stock_attempt(task, budget, connection, *, max_steps=STOCK_STEPS,
                        max_output=STOCK_OUTPUT_TOKENS, timeout=STOCK_TASK_SECONDS):
    from run_agent import MODEL, snapshot_tests, restore_tests, tests_pass
    tests = snapshot_tests(task)
    error = None
    result = {}
    try:
        agent = stock_agent(budget, connection, MODEL, str(task.cwd), max_steps=max_steps, max_output=max_output)
        result = await asyncio.wait_for(agent.invoke({'query': task.query, 'conversation_id': uuid.uuid4().hex}), timeout)
    except Exception as exc:
        error = exc
    finally:
        changed = restore_tests(tests)
        (task.cwd / 'answer.txt').unlink(missing_ok=True)
    if changed:
        return 'failed', 'agent edited tests'
    if task.type == 'coding' and tests_pass(task):
        return 'solved', 'DONE'
    if error:
        raise error
    final = str(result.get('output', '') if isinstance(result, dict) else result).strip()
    if isinstance(result, dict) and result.get('stop_reason'):
        return 'failed', str(result['stop_reason'])
    if final == 'Max iterations reached without completion':
        return 'failed', 'step limit'
    if 'IMPOSSIBLE' in final:
        return 'impossible', ''
    if task.type == 'coding':
        return 'failed', 'tests still fail'
    return ('solved', final.splitlines()[-1].strip()) if final else ('failed', 'empty answer')


async def run(root, output, variant, *, stock_steps=STOCK_STEPS, stock_output=STOCK_OUTPUT_TOKENS,
              stock_seconds=STOCK_TASK_SECONDS, run_seconds=3300):
    from importlib.metadata import version
    from runtime.budget import Budget, Journal
    from runtime.metered_model import MeteredModel
    from runtime.oj_agent import Connection, react_agent
    from runtime.tasks import load_task, save_answer
    from runtime.attempt_policy import limits_for_task
    from run_agent import MODEL, attempt
    configuration = dict(variant=variant, model=MODEL, stock_steps=stock_steps,
        stock_output_tokens=stock_output, stock_task_seconds=stock_seconds,
        run_seconds=run_seconds, global_budget_authority='proxy',
        dependencies=dict(openjiuwen=version('openjiuwen'), filelock=version('filelock')))
    config_path = output/'config.json'
    if config_path.exists() and json.loads(config_path.read_text(encoding='utf-8')) != configuration:
        raise ValueError('Cannot resume a run with different settings; use a new output directory')
    config_path.write_text(json.dumps(configuration, indent=2)+'\n', encoding='utf-8')
    connection = Connection(os.environ['LLM_BASE_URL'], os.environ.pop('LLM_API_KEY'))
    journal = Journal(output/'usage.jsonl')
    budget = Budget(100000, journal)  # informational; actual global cutoff belongs to proxy
    original = MeteredModel._charge
    def exact_charge(self, messages, tools, message):
        usage = getattr(message, 'usage_metadata', None)
        inp = getattr(usage, 'input_tokens', None)
        out = getattr(usage, 'output_tokens', None)
        if inp is not None and out is not None and (inp or out):
            self._budget.charge(self._name, int(inp), int(out), False)
        else:
            original(self, messages, tools, message)
    MeteredModel._charge = exact_charge
    result_path = output/'results.jsonl'
    previous = [json.loads(x) for x in result_path.read_text(encoding='utf-8').splitlines()] if result_path.exists() else []
    completed = {x['id'] for x in previous}
    budget.spent = sum(x['cost'] for x in previous)
    started = time.monotonic()
    deadline = started + run_seconds
    stop = 'all tasks handled'
    errors = 0
    for source in sorted(root.iterdir()):
        if not (source/'task.json').exists() or source.name in completed:
            continue
        if time.monotonic() >= deadline:
            stop = 'run time limit'
            break
        work = output/'tasks'/source.name
        if work.exists():
            raise RuntimeError('Partial task directory exists: '+str(work))
        shutil.copytree(source, work)
        task = load_task(work)
        assert 'expected' not in json.loads((work/'task.json').read_text(encoding='utf-8'))
        before = budget.spent
        task_start = time.monotonic()
        attempts = []
        row = dict(id=task.id, type=task.type, reward=task.reward, variant=variant,
                   status='failed', answer='', error='run time limit')
        transient = False
        for retry in range(2):
            remaining = deadline-time.monotonic()
            if remaining <= 0:
                break
            limits = limits_for_task(task.type)
            budget.begin_task(task.id, limits.initial_cost if variant == 'ours' else float('inf'),
                hard_limit=limits.cost if variant == 'ours' else float('inf'))
            row = dict(id=task.id, type=task.type, reward=task.reward, variant=variant, status='failed', answer='', error=None)
            try:
                row['status'], row['answer'] = await (attempt(task, budget, connection, react_agent, limits, timeout=remaining)
                    if variant == 'ours' else stock_attempt(task, budget, connection,
                        max_steps=stock_steps, max_output=stock_output, timeout=min(stock_seconds, remaining)))
            except Exception as exc:
                row['error'] = f'{type(exc).__name__}: {exc}'[:800]
            finally:
                attempt_cost = budget.end_task()
            attempts.append(dict(status=row['status'], error=row['error'], cost=round(attempt_cost, 2)))
            transient = row['error'] and any(t in row['error'].lower() for t in ('503','502','429','overloaded','connection error'))
            if transient and retry == 0 and deadline-time.monotonic() > 15:
                journal.write('infrastructure_retry', task=task.id, error=row['error'])
                await asyncio.sleep(15)
                # A retry starts from the original task, never from a failed edited solution.
                for item in source.rglob('*'):
                    if item.is_file():
                        target = work/item.relative_to(source)
                        target.parent.mkdir(parents=True, exist_ok=True)
                        shutil.copy2(item, target)
                continue
            break
        if row['status'] == 'solved':
            save_answer(task, row['answer'])
        row.update(cost=round(budget.spent-before, 2), seconds=round(time.monotonic()-task_start, 2), attempts=attempts)
        with result_path.open('a', encoding='utf-8') as stream:
            stream.write(json.dumps(row, ensure_ascii=False)+'\n')
        print('BENCH', json.dumps(row, ensure_ascii=False), flush=True)
        errors = errors+1 if row['error'] and transient else 0
        if errors >= 4:
            stop = 'consecutive infrastructure errors'
            break
    journal.write('benchmark_finish', variant=variant, spent=budget.spent,
        seconds=time.monotonic()-started, stop=stop, configuration=configuration)


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.ArgumentDefaultsHelpFormatter)
    p.add_argument('--input', type=Path, required=True)
    p.add_argument('--output', type=Path, required=True)
    p.add_argument('--variant', choices=['stock','ours'], required=True)
    p.add_argument('--stock-steps', type=int, default=STOCK_STEPS, help='Native ReAct iteration cap')
    p.add_argument('--stock-output-tokens', type=int, default=STOCK_OUTPUT_TOKENS, help='Maximum output per model call')
    p.add_argument('--stock-task-seconds', type=float, default=STOCK_TASK_SECONDS, help='Maximum seconds per stock task')
    p.add_argument('--run-seconds', type=float, default=3300)
    args = p.parse_args()
    if min(args.stock_steps, args.stock_output_tokens, args.stock_task_seconds, args.run_seconds) <= 0:
        p.error('Limits must be positive')
    root, output = args.input.resolve(), args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    os.chdir(tempfile.mkdtemp(prefix='stock-comparison-'))
    asyncio.run(run(root, output, args.variant, stock_steps=args.stock_steps,
        stock_output=args.stock_output_tokens, stock_seconds=args.stock_task_seconds, run_seconds=args.run_seconds))
