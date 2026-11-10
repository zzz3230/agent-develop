"""SQL execution through stock BashTool and OJ's native completion hook."""
from __future__ import annotations

import json
import os
import re
import shlex
from pathlib import Path

from openjiuwen.core.single_agent.rail.base import AgentRail

from runtime.profiles import ANSWER_RULES
from runtime.sql_tables import RESULT_PREFIX

SQL_SYSTEM = (
    'Use SQL for this CSV task. The SQLite helper is already installed and the supplied schema is complete. '
    'Your FIRST tool call MUST run the SQL helper below. Do not run ls, head, cat or a Python CSV computation first. '
    'The helper itself is Python, satisfying any instruction to use bash with Python. '
    'CSV tables in SQLite have TEXT columns; '
    'use CAST for numeric comparisons and sorting. Run a single scalar SELECT using the stock bash tool: '
    'python3 -m runtime.sql_tables --query "YOUR SQL" --final\n'
    'Quote identifiers with double quotes inside SQL when needed and shell-quote the whole query correctly. '
    'Use --final ONLY when the query computes the requested final answer. '
    'For exploratory counts, checks or probes, omit --final; those do NOT complete the task. '
    'Never submit a row count or SELECT 1 as final unless that is the question. '
    'A successful --final result completes the task automatically; no final model call is needed. '
    'On SQL errors, repair the query. Only after an actual SQL error, if the computation is unsupported, '
    'you may fall back to Python through bash. '
    'Exact decimal helpers: DEC_MUL(a,b,...) returns a decimal string; DEC_SUB(a,b) subtracts decimal values; '
    'CENTS(x) rounds a decimal currency amount HALF_UP to integer cents. Avoid SQLite REAL for exact money. '
    + ANSWER_RULES
)


class SqlCompletionRail(AgentRail):
    def init(self, agent):
        package_root = str(Path(__file__).resolve().parent.parent)
        paths = os.environ.get('PYTHONPATH', '').split(os.pathsep)
        os.environ['PYTHONPATH'] = os.pathsep.join(dict.fromkeys([package_root] + [p for p in paths if p]))

    async def after_tool_call(self, ctx):
        inputs = ctx.inputs
        if inputs.tool_name != 'bash':
            return
        if getattr(inputs.tool_result, 'success', True) is False:
            return
        args = inputs.tool_args
        if isinstance(args, str):
            try:
                args = json.loads(args)
            except ValueError:
                return
        try:
            words = shlex.split((args or {}).get('command', ''))
        except ValueError:
            return
        # Accept only the dedicated CLI command, not arbitrary printed markers.
        if len(words) != 6 or words[0] not in ('python', 'python3') or words[1:4] != ['-m', 'runtime.sql_tables', '--query'] or words[-1] != '--final':
            return
        result = str(getattr(inputs.tool_msg, 'content', '') or '')
        match = re.search(r'(?:^|\n)(?:Stdout: *)?' + RESULT_PREFIX + r'([^\r\n]+)', result)
        if match:
            try:
                value = json.loads(match[1])
            except ValueError:
                return
            if type(value) in (str, int, float) and str(value).strip():
                ctx.request_force_finish({'output': str(value), 'result_type': 'answer'})
