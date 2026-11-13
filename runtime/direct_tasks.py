"""Short first attempts for tasks that can be checked locally before using the agent."""
from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

from openjiuwen.core.foundation.llm import ModelRequestConfig

from runtime.metered_model import MeteredModel
from runtime.search_context import search_context


def plain(text: str) -> str:
    value = text.strip()
    block = re.fullmatch(r"```(?:python|json)?\s*\n(.*?)\n```", value, re.I | re.S)
    return block.group(1).strip() if block else value


async def ask(connection, budget, model_name: str, system: str, user: str, max_output: int):
    model = MeteredModel(connection.client(), ModelRequestConfig(
        model=model_name, temperature=0.0, max_tokens=max_output), budget)
    reply = await model.invoke([{"role": "system", "content": system},
                                {"role": "user", "content": user}])
    return plain(str(getattr(reply, "content", "") or ""))


MATH_SYSTEM = (
    "Write only a Python program that computes the exact final answer to the whole question "
    "and prints it on one line. No Markdown, explanation, imports, file access, or tool calls. "
    "math, Fraction, and Decimal are available. Include every adjustment stated in the question. "
    "If the answer cannot be computed exactly, reply UNSUPPORTED."
)


def _math_limit():
    try:
        import resource
        resource.setrlimit(resource.RLIMIT_CPU, (5, 5))
        resource.setrlimit(resource.RLIMIT_AS, (512 << 20, 512 << 20))
        resource.setrlimit(resource.RLIMIT_FSIZE, (0, 0))
    except (ImportError, OSError, ValueError):
        pass


async def math(cwd: Path, question: str, check: str, connection, budget, model_name: str) -> str | None:
    hint = "Print an integer." if check == "exact_int" else "Print exactly the requested value."
    code = await ask(connection, budget, model_name, MATH_SYSTEM, question + "\n" + hint, 850)
    if not code or code == "UNSUPPORTED" or len(code) > 6000:
        return None
    worker = Path(__file__).with_name("direct_math_worker.py")
    done = subprocess.run([sys.executable, "-I", "-S", "-B", str(worker)], input=code,
                          capture_output=True, text=True, encoding="utf-8", errors="replace",
                          cwd=cwd, env={"PYTHONIOENCODING": "utf-8"}, timeout=7,
                          preexec_fn=_math_limit if sys.platform != "win32" else None)
    lines = done.stdout.splitlines()
    return lines[0].strip() if done.returncode == 0 and len(lines) == 1 and len(lines[0]) <= 200 else None


SEARCH_SYSTEM = (
    "Answer the question using only the supplied file excerpts. Return just the exact answer "
    "as it appears in the source, on one line. If the excerpts do not establish a unique answer, "
    "reply UNSUPPORTED. Do not run tools or guess."
)


async def search(cwd: Path, question: str, connection, budget, model_name: str) -> str | None:
    context = search_context(cwd, question)
    if not context:
        return None
    excerpts = context.partition("\n")[2]
    answer = await ask(connection, budget, model_name, SEARCH_SYSTEM,
                       question + "\n\nFile excerpts:\n" + excerpts, 300)
    if not answer or answer == "UNSUPPORTED" or len(answer) > 200 or "\n" in answer:
        return None
    answer = answer.strip("`\"'")
    return answer if answer and answer.casefold() in excerpts.casefold() else None


CODING_SYSTEM = (
    "Repair the Python code so the stated behavior and the tests hold. Reply with exactly one "
    "JSON object with keys old and new: old is an exact substring of the source file, new is its "
    "replacement. Change the smallest relevant code region. Do not edit tests. If one replacement "
    "is insufficient or you cannot determine a safe repair, reply UNSUPPORTED."
)


async def coding(cwd: Path, question: str, tests_pass, connection, budget, model_name: str) -> str | None:
    sources = [p for p in cwd.rglob("*.py") if not p.name.startswith("test_") and p.name != "__init__.py"]
    tests = [p for p in cwd.rglob("test_*.py")]
    if len(sources) != 1 or not tests:
        return None
    target = sources[0]
    if cwd.resolve() not in target.resolve().parents:
        return None
    original = target.read_text(encoding="utf-8")
    test_text = "\n\n".join(f"[{p.relative_to(cwd)}]\n{p.read_text(encoding='utf-8')}" for p in tests)
    if len(original) + len(test_text) > 10000:
        return None
    user = f"Task: {question}\n\n[{target.relative_to(cwd)}]\n{original}\n\nTests:\n{test_text}"
    reply = await ask(connection, budget, model_name, CODING_SYSTEM, user, 950)
    try:
        patch = json.loads(reply)
    except (TypeError, ValueError):
        return None
    if not isinstance(patch, dict) or set(patch) != {"old", "new"}:
        return None
    old, new = patch["old"], patch["new"]
    if not isinstance(old, str) or not isinstance(new, str) or not old or old == new:
        return None
    if original.count(old) != 1 or len(new) > len(old) + 3000:
        return None
    target.write_text(original.replace(old, new, 1), encoding="utf-8")
    success = False
    try:
        success = tests_pass()
        if success:
            return "DONE"
    finally:
        if not success:
            target.write_text(original, encoding="utf-8")
    return None
