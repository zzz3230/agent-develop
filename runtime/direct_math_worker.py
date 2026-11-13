"""Run a model-generated calculation with a small set of pure Python operations."""
from __future__ import annotations

import ast
import builtins
import decimal
import fractions
import math
import sys


def main() -> int:
    source = sys.stdin.read(6001)
    if len(source) > 6000:
        return 2
    try:
        tree = ast.parse(source, mode="exec")
    except SyntaxError:
        return 2
    forbidden = (ast.Import, ast.ImportFrom, ast.ClassDef, ast.With, ast.AsyncWith,
                 ast.Try, ast.Raise, ast.Delete, ast.Global, ast.Nonlocal, ast.AsyncFunctionDef,
                 ast.Await, ast.Yield, ast.YieldFrom)
    for node in ast.walk(tree):
        if isinstance(node, forbidden):
            return 2
        if isinstance(node, ast.Name) and node.id.startswith("_"):
            return 2
        if isinstance(node, ast.Attribute) and node.attr.startswith("_"):
            return 2
        if isinstance(node, ast.FunctionDef) and (node.decorator_list or node.name.startswith("_")):
            return 2
    allowed = {name: getattr(builtins, name) for name in (
        "print", "range", "len", "sum", "min", "max", "abs", "pow", "divmod", "int",
        "float", "str", "bool", "enumerate", "zip", "sorted", "all", "any", "round",
        "list", "tuple", "dict", "set", "reversed", "isinstance",
    )}
    scope = {"__builtins__": allowed, "math": math, "Fraction": fractions.Fraction,
             "Decimal": decimal.Decimal}
    try:
        exec(compile(tree, "<calculation>", "exec"), scope)
    except Exception:
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
