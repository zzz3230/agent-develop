"""Zero-token check for coding tasks whose visible tests no honest fix can pass.

Only proven contradictions between two assertions on the same literal call are reported:
  assertEqual(f(100), 120)   and  assertEqual(f(100), 121)
  assertEqual(f(7), '007')   and  assertIsInstance(f(7), int)
  assertEqual(f(1), 3)       and  assertNotEqual(f(1), 3)
Expected values are compared as values (1 == 1.0 is not a contradiction). Calls with
non-literal arguments, methods of objects and anything built in loops are ignored: when in
doubt the task goes to the agent as usual. A function with hidden state could still satisfy
such tests, so the queue only moves a flagged task to the end; it never drops it.
"""
from __future__ import annotations

import ast
from pathlib import Path

_TYPES = {'int': int, 'str': str, 'float': float, 'list': list, 'dict': dict, 'tuple': tuple,
          'bool': bool, 'set': set, 'bytes': bytes}
_MISSING = object()


def _literal(node):
    try:
        return ast.literal_eval(node)
    except (ValueError, TypeError, SyntaxError, MemoryError, RecursionError):
        return _MISSING


def _imported(tree) -> set[str]:
    names = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            names |= {(a.asname or a.name).split('.')[0] for a in node.names}
    return names


def _plain_call(node, imported: set[str]) -> str | None:
    """`f(1, 'a')` or `module.f(x=2)`: an imported function with literal arguments; its source, else None.

    Calls without arguments (`next_id()`) and methods of local objects are left alone: those
    are the usual stateful interfaces, where two different results are legitimate.
    """
    if not isinstance(node, ast.Call) or not (node.args or node.keywords):
        return None
    func = node.func
    owner = func if isinstance(func, ast.Name) else func.value if isinstance(func, ast.Attribute) else None
    if not isinstance(owner, ast.Name) or owner.id not in imported:
        return None
    if any(isinstance(a, ast.Starred) or _literal(a) is _MISSING for a in node.args):
        return None
    if any(k.arg is None or _literal(k.value) is _MISSING for k in node.keywords):
        return None
    return ast.unparse(node)


def _can_be(value, expected: type) -> bool:
    """Could some instance of `expected` equal `value`? Numbers compare across types: 7 == 7.0."""
    if isinstance(value, (int, float)) and expected in (int, float, bool):
        return True
    return isinstance(value, expected)


def _contradiction(source: str) -> str | None:
    try:
        tree = ast.parse(source)
    except (SyntaxError, ValueError, RecursionError):
        return None
    imported = _imported(tree)
    equal: dict[str, list] = {}
    unequal: dict[str, list] = {}
    kinds: dict[str, list[str]] = {}
    for node in ast.walk(tree):
        if not (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and len(node.args) >= 2):
            continue
        name, (first, second) = node.func.attr, node.args[:2]
        if name in ('assertEqual', 'assertNotEqual'):
            # The call may be either argument: assertEqual(f(1), 2) or assertEqual(2, f(1)).
            call, other = ((_plain_call(first, imported), second) if _plain_call(first, imported)
                           else (_plain_call(second, imported), first))
            value = _literal(other)
            if call and value is not _MISSING:
                (equal if name == 'assertEqual' else unequal).setdefault(call, []).append(value)
        elif name == 'assertIsInstance' and isinstance(second, ast.Name) and second.id in _TYPES:
            call = _plain_call(first, imported)
            if call:
                kinds.setdefault(call, []).append(second.id)
    for call, values in equal.items():
        for i, a in enumerate(values):
            if any(a != b for b in values[i+1:]):
                return f'{call} must equal both {a!r} and {next(b for b in values[i+1:] if a != b)!r}'
            if any(a == b for b in unequal.get(call, [])):
                return f'{call} must equal and not equal {a!r}'
            for kind in kinds.get(call, []):
                if not _can_be(a, _TYPES[kind]):
                    return f'{call} must equal {a!r} and be an instance of {kind}'
    return None


def contradictory_tests(root: Path, max_files: int = 20, max_bytes: int = 200_000) -> str | None:
    """A short reason if some test file under root contradicts itself, else None. Never raises."""
    try:
        files = sorted(p for p in root.rglob('test*.py') if p.is_file() and not p.is_symlink())[:max_files]
    except OSError:
        return None
    for path in files:
        try:
            if path.stat().st_size > max_bytes:
                continue
            reason = _contradiction(path.read_text(encoding='utf-8', errors='replace'))
        except OSError:
            continue
        if reason:
            return f'{path.name}: {reason}'[:300]
    return None
