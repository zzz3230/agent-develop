"""Measured prompt profiles; shared final-answer format across task types."""

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


def system_for_task(task_type: str) -> str:
    return ECONOMY_SYSTEM if task_type == "coding" else BASELINE_SYSTEM
