"""Measured prompt profiles; shared final-answer format across task types."""
import os

ANSWER_RULES = (
    "Your last message must be only the final answer on one line, without explanation, labels, Markdown, or code fences. "
    "For a numeric answer, return only the number. For code repair, return DONE after running the tests. "
    "Return IMPOSSIBLE if the data cannot give an exact answer. Do not create answer.txt."
)
BASELINE_SYSTEM = "Solve the task with the tools in as few steps as possible. " + ANSWER_RULES
ECONOMY_SYSTEM = (
    "Solve correctly while minimizing total token usage. "
    "Combine related operations into one tool call when practical. "
    "Print only the tool output needed to solve the task. "
    "Avoid repeating successful computations. "
    "For code repairs, run the tests after editing. " + ANSWER_RULES
)


# Measured on planner-500 pools: the model usually sees the gap in its first two tool calls and
# then spends the rest of the attempt looking for hidden data. IMPOSSIBLE_RULES=1 tells it when to stop.
GAP_RULES = (
    " Everything the task needs is in the task text and the current directory. "
    "Reply IMPOSSIBLE as soon as the data you have read cannot give one exact answer: the person, record, "
    "field, column, rate, file or quantity the question needs is absent; records that must be unique disagree; "
    "or sources of equal standing state different values. An empty selection or a zero total is an answer, not a gap. Before that, check once for an obvious variant "
    "(a misspelled or differently named file, column or name, other letter case). Do not search for hidden "
    "files, metadata, timestamps or anything outside the current directory, do not guess or brute-force "
    "a missing value, and do not repeat a check that already gave the same result."
)
CODING_GAP_RULES = (
    " If the tests demand incompatible results from the same call, so no implementation can pass them all, "
    "reply IMPOSSIBLE instead of editing further."
)


def system_for_task(task_type: str) -> str:
    economy = os.environ.get("PROMPT_ECONOMY", "1") == "1"  # 0: baseline everywhere, for A/B
    system = ECONOMY_SYSTEM if economy and task_type == "coding" else BASELINE_SYSTEM
    if os.environ.get("IMPOSSIBLE_RULES", "0") == "1":
        system += CODING_GAP_RULES if task_type == "coding" else GAP_RULES
    return system
