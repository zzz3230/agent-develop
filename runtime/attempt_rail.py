"""Native OJ hooks: bounded commands and repeated errors without file progress."""
import hashlib
import json
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
    def __init__(self, root: Path, limits: AttemptLimits, journal=None):
        self.root, self.limits, self.journal = root, limits, journal
        self.state = source_state(root)
        self.errors = {}

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
        if getattr(result, 'success', None) is not False:
            return
        text = str(getattr(ctx.inputs.tool_msg, 'content', '') or getattr(result, 'error', ''))
        args = ctx.inputs.tool_args
        if isinstance(args, str):
            args = json.loads(args)
        meaningful = {k:v for k,v in (args or {}).items() if k in {'command','workdir','shell_type'}}
        signature = json.dumps([ctx.inputs.tool_name, meaningful, text], sort_keys=True, default=str)
        key = hashlib.sha256(signature.encode()).hexdigest()
        self.errors[key] = self.errors.get(key, 0) + 1
        if self.errors[key] >= self.limits.repeated_errors:
            if self.journal:
                self.journal.write('attempt_stop', reason='repeated_tool_error', repeats=self.errors[key])
            ctx.request_force_finish({'output':'', 'result_type':'failed', 'stop_reason':'repeated_tool_error'})
