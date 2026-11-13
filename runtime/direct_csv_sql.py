"""Single model request for a CSV scalar; the regular task agent handles failures."""
from __future__ import annotations

import re
import sqlite3
from pathlib import Path

from openjiuwen.core.foundation.llm import ModelRequestConfig

from runtime.metered_model import MeteredModel
from runtime.sql_tables import scalar


SYSTEM = (
    "Translate the user's CSV question into exactly one read-only SQLite SELECT that returns "
    "one non-NULL cell: the final answer. Reply with SQL only, without Markdown or explanation. "
    "All CSV columns are stored as TEXT; CAST numeric values before arithmetic or comparison. "
    "For exact decimal arithmetic use DEC_MUL, DEC_SUB, or CENTS when appropriate. "
    "Use only the supplied tables and columns and account for every condition in the question. "
    "If the question cannot be answered with the supplied CSV data, reply UNSUPPORTED."
)


def sql_text(reply: str) -> str | None:
    text = reply.strip()
    match = re.fullmatch(r"```(?:sql)?\s*\n(.*?)\n```", text, flags=re.I | re.S)
    if match:
        text = match.group(1).strip()
    if not re.match(r"^(?:SELECT|WITH)\b", text, re.I) or not re.search(r"\bFROM\b", text, re.I):
        return None
    return text


async def solve(cwd: Path, question_and_schema: str, check: str, connection, budget, model_name: str,
                max_output: int = 700) -> str | None:
    request = ModelRequestConfig(model=model_name, temperature=0.0, max_tokens=max_output)
    model = MeteredModel(connection.client(), request, budget)
    required = {
        "exact_int": "The SQL result must be a single integer, with no decimal part or units.",
        "exact_str": "The SQL result must be one exact text value from the data.",
    }.get(check, "The SQL result must be one answer value.")
    reply = await model.invoke([
        {"role": "system", "content": SYSTEM},
        {"role": "user", "content": question_and_schema + "\n" + required},
    ])
    query = sql_text(str(getattr(reply, "content", "") or ""))
    if query is None:
        budget.journal.write("direct_csv_sql", task=budget.task_id, status="unsupported")
        return None
    try:
        answer = str(scalar(cwd, query)).strip()
    except (ValueError, TypeError, OverflowError, sqlite3.Error) as exc:
        budget.journal.write("direct_csv_sql", task=budget.task_id, status="invalid_sql",
                             error=f"{type(exc).__name__}: {exc}"[:200])
        return None
    budget.journal.write("direct_csv_sql", task=budget.task_id, status="scalar")
    return answer
