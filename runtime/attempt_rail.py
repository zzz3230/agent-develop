"""Native OJ hooks: bounded commands and repeated errors without file progress."""
import hashlib
import json
import re
import time
from pathlib import Path

from openjiuwen.core.single_agent.rail.base import AgentRail
from runtime.attempt_policy import AttemptLimits


def source_state(root: Path) -> str:
    digest = hashlib.sha256()
    files = sorted(p for p in root.rglob('*') if p.is_file() and not p.is_symlink() and '__pycache__' not in p.parts
                   and p.suffix in {'.py','.js','.ts','.java','.cpp','.c','.rs','.go','.json','.yaml','.toml'})[:100]
    for path in files:
        if path.name == 'task.json':
            continue
        try:
            stat = path.stat()
            digest.update(str(path.relative_to(root)).encode())
            if stat.st_size <= 200_000:
                digest.update(path.read_bytes())
            else:
                digest.update(f'{stat.st_size}:{stat.st_mtime_ns}'.encode())
        except OSError:
            continue
    return digest.hexdigest()


class AttemptRail(AgentRail):
    def __init__(self, root: Path, limits: AttemptLimits, journal=None, budget=None, task_type=''):
        self.root, self.limits, self.journal = root, limits, journal
        self.state = source_state(root)
        self.errors = {}
        self.budget, self.task_type = budget, task_type
        self.hard_cost = min(limits.cost, budget.task_hard_limit) if budget else limits.cost
        self.allowed_steps = min(limits.initial_steps, limits.steps)
        self.allowed_cost = min(limits.initial_cost, self.hard_cost, budget.task_limit if budget else float('inf'))
        self.allowed_seconds = min(limits.initial_seconds, limits.seconds)
        self.started = time.monotonic()
        self.extensions = 0
        self.fresh_progress = set()
        self.seen_outputs = set()
        self.test_failures = None

    async def before_model_call(self, ctx):
        step = int(ctx.extra.get('_react_iteration', 1))
        spent = self.budget.task_spent if self.budget else 0
        elapsed = time.monotonic() - self.started
        hit = ('task_cost_limit' if spent >= self.allowed_cost else
               'no_progress_step_limit' if step > self.allowed_steps else
               'no_progress_time_limit' if elapsed >= self.allowed_seconds else None)
        if hit is None:
            return
        if self.fresh_progress and self.extensions < self.limits.max_extensions:
            new_cost = min(self.hard_cost, self.allowed_cost + self.limits.cost_increment)
            new_steps = min(self.limits.steps, self.allowed_steps + self.limits.step_increment)
            new_seconds = min(self.limits.seconds, self.allowed_seconds + self.limits.time_increment)
            if spent < new_cost and step <= new_steps and elapsed < new_seconds:
                self.allowed_cost, self.allowed_steps, self.allowed_seconds = new_cost, new_steps, new_seconds
                self.extensions += 1
                if self.budget:
                    self.budget.extend_task_limit(new_cost)
                if self.journal:
                    self.journal.write('attempt_extended', task=self.budget.task_id if self.budget else None,
                        evidence=sorted(self.fresh_progress), steps=new_steps, cost=new_cost,
                        seconds=new_seconds, extensions=self.extensions)
                self.fresh_progress.clear()
                return
        if self.journal:
            self.journal.write('attempt_stop', task=self.budget.task_id if self.budget else None, reason=hit)
        ctx.request_force_finish({'output':'', 'result_type':'failed', 'stop_reason':hit})

    def observe_progress(self, text: str, args: dict, success: bool) -> None:
        if self.task_type == 'coding':
            if re.search(r'Ran \d+ tests? in .*?\n\s*OK\b', text):
                self.fresh_progress.add('tests_passed')
            failed = re.search(r'FAILED \(([^)]+)\)', text)
            if failed:
                count = sum(int(n) for n in re.findall(r'(?:failures|errors)=(\d+)', failed[1]))
                if count and self.test_failures is not None and count < self.test_failures:
                    self.fresh_progress.add('fewer_failing_tests')
                if count:
                    self.test_failures = count if self.test_failures is None else min(count, self.test_failures)
            return
        if not success:
            return
        match = re.search(r'\nStdout:\s*(.*?)\nStderr:', text, re.S)
        payload = match[1].strip() if match else ''
        if not payload or payload == '(empty)':
            return
        key = hashlib.sha256(payload.encode()).hexdigest()
        if key in self.seen_outputs:
            return
        self.seen_outputs.add(key)
        if re.fullmatch(r'[+-]?\d+(?:\.\d+)?', payload):
            self.fresh_progress.add('computed_scalar')
        elif self.task_type == 'search' and len(payload) >= 40 and re.search(r'\b(cat|grep|head|tail|read_text)\b', args.get('command','')):
            self.fresh_progress.add('new_source_excerpt')
        elif self.task_type == 'data_analysis' and re.search(r'\b(rows|matched|total|sum|count|result|revenue)\b[^\n]*\d', payload, re.I):
            self.fresh_progress.add('intermediate_computation')

    async def before_tool_call(self, ctx):
        if ctx.inputs.tool_name != 'bash':
            return
        args = ctx.inputs.tool_args
        was_json = isinstance(args, str)
        if isinstance(args, str):
            args = json.loads(args)
        args = dict(args or {})
        try:
            requested = int(args.get('timeout') or self.limits.command_seconds)
        except (TypeError, ValueError):
            requested = self.limits.command_seconds
        args['timeout'] = max(1, min(requested, self.limits.command_seconds))
        args['run_in_background'] = False
        ctx.inputs.tool_args = json.dumps(args) if was_json else args

    async def after_tool_call(self, ctx):
        current = source_state(self.root)
        if current != self.state:
            self.errors.clear()
            self.state = current
        result = ctx.inputs.tool_result
        text = str(getattr(ctx.inputs.tool_msg, 'content', '') or getattr(result, 'error', ''))
        args = ctx.inputs.tool_args
        if isinstance(args, str):
            args = json.loads(args)
        self.observe_progress(text, args or {}, getattr(result, 'success', None) is True)
        if getattr(result, 'success', None) is not False:
            return
        text = re.sub(r'(Ran \d+ tests? in )[\d.]+s', r'\1<TIME>s', text)
        meaningful = {k:v for k,v in (args or {}).items() if k in {'command','workdir','shell_type'}}
        signature = json.dumps([ctx.inputs.tool_name, meaningful, text], sort_keys=True, default=str)
        key = hashlib.sha256(signature.encode()).hexdigest()
        self.errors[key] = self.errors.get(key, 0) + 1
        if self.errors[key] >= self.limits.repeated_errors:
            if self.journal:
                self.journal.write('attempt_stop', reason='repeated_tool_error', repeats=self.errors[key])
            ctx.request_force_finish({'output':'', 'result_type':'failed', 'stop_reason':'repeated_tool_error'})
