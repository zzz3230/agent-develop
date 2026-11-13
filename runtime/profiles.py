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


# IMPOSSIBLE_PROMPT=1: concrete, per-type grounds for refusing. The agent usually sees the gap on
# its first or second step and then keeps searching or assumes a value; an unsolvable task earns
# nothing, so every token after that point is lost.
IMPOSSIBLE_COMMON = (
    " Some tasks cannot be solved. As soon as you see that, stop and reply with the single word IMPOSSIBLE: "
    "do not look outside the current directory, and never guess, estimate or assume a missing value."
)
IMPOSSIBLE_BY_TYPE = {
    "math": (
        " Before computing, check the statement: reply IMPOSSIBLE if a quantity the question needs is not given, "
        "if two statements conflict, or if the asked quantity is unrelated to the given ones or not exactly known."
    ),
    "data_analysis": (
        " Reply IMPOSSIBLE if a file or column the question needs does not exist, or if the data breaks a rule "
        "the task states. A misspelled file or column name with one obvious match is not a reason: use the match."
    ),
    "search": (
        " Reply IMPOSSIBLE if the files have no record of the asked person, thing or fact, or if equally valid "
        "records disagree. First check spelling variants and whether one record corrects or replaces another."
    ),
    "coding": (
        " Reply IMPOSSIBLE if two tests demand different results from the same call, or a test demands something "
        "no ordinary implementation can return. Do not special-case the tests or add hidden state to satisfy them."
    ),
}
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
    if os.environ.get("IMPOSSIBLE_PROMPT") == "1":
        system += IMPOSSIBLE_COMMON + IMPOSSIBLE_BY_TYPE.get(task_type, "")
    if os.environ.get("IMPOSSIBLE_RULES", "0") == "1":
        system += CODING_GAP_RULES if task_type == "coding" else GAP_RULES
    return system
