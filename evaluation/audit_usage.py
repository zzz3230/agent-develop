"""Check whether the production character estimate would exceed reported output usage.

Reads OJ's recorded response representations with ast.parse; never evaluates them.
For this no-reasoning benchmark all reasoning_tokens must be zero.
"""
import argparse
import ast
import json
from pathlib import Path


def _lines(console: Path):
    with console.open('rb') as stream:
        prefix = stream.read(2)
    encoding = 'utf-16' if prefix in (b'\xff\xfe', b'\xfe\xff') else 'utf-8'
    with console.open(encoding=encoding) as stream:
        yield from stream


def audit(console: Path):
    responses = 0
    overestimates = []
    nonzero_reasoning = 0
    for line in _lines(console):
        start = line.find('{"event_id":')
        if start < 0:
            continue
        try:
            event = json.loads(line[start:])
            response = event.get('metadata', {}).get('response')
            if not response:
                continue
            tree = ast.parse(response, mode='eval')
        except (ValueError, SyntaxError):
            continue
        produced, reported = '', None
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            name = getattr(node.func, 'id', '')
            fields = {k.arg: k.value for k in node.keywords}
            if name == 'ChatCompletionMessage':
                value = fields.get('content')
                produced += value.value if isinstance(value, ast.Constant) and isinstance(value.value, str) else ''
            elif name == 'Function':
                for key in ('name', 'arguments'):
                    value = fields.get(key)
                    produced += value.value if isinstance(value, ast.Constant) and isinstance(value.value, str) else ''
            elif name == 'CompletionUsage':
                value = fields.get('completion_tokens')
                reported = value.value if isinstance(value, ast.Constant) else None
            elif name == 'CompletionTokensDetails':
                value = fields.get('reasoning_tokens')
                nonzero_reasoning += bool(isinstance(value, ast.Constant) and value.value)
        if reported is not None:
            responses += 1
            estimate = len(produced)//4 + 1
            if estimate > reported:
                overestimates.append(dict(call=responses, reported=reported,
                    estimated=estimate, extra=estimate-reported))
    return dict(responses=responses, overestimated_calls=len(overestimates),
                extra_cost=sum(x['extra'] for x in overestimates),
                overestimates=overestimates, nonzero_reasoning_calls=nonzero_reasoning)


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('console', type=Path)
    args = p.parse_args()
    print(json.dumps(audit(args.console)))
