"""Checks gaps-v1 without any model. Run from the repository root:

    python benchmarks/gaps-v1/validate.py

1. Agent inputs: official fields only, official instruction tails, no IMPOSSIBLE hint, hash matches.
2. Code references: buggy mylib fails the visible tests, the reference passes visible and
   private tests, a narrow fix passes visible tests but fails private ones.
3. Self-grade with evaluation/grade: perfect answers score the maximum; answering every
   impossible task is flagged; narrow code fixes lose the hidden-test tasks.
"""
from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent
REPO = ROOT.parents[1]
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(ROOT))

from build import COMMON, CODE_INSTRUCTION  # noqa: E402
from evaluation.grade import grade  # noqa: E402

OFFICIAL_FIELDS = {"task_id", "task_type", "instruction", "reward", "check"}
failures: list[str] = []


def check(condition: bool, message: str) -> None:
    if not condition:
        failures.append(message)


def run_python(args: list[str], cwd: Path) -> int:
    return subprocess.run([sys.executable, "-B", *args], cwd=cwd, capture_output=True, timeout=60).returncode


def code_case(ref_dir: Path, mylib: Path | None, with_private: bool) -> bool:
    """True if visible (+ private) tests pass with the given mylib."""
    with tempfile.TemporaryDirectory() as temp:
        work = Path(temp)
        shutil.copytree(ref_dir / "workspace", work, dirs_exist_ok=True)
        if mylib:
            shutil.copy2(mylib, work / "mylib.py")
        if with_private:
            shutil.copy2(ref_dir / "test_private.py", work / "test_private.py")
        return run_python(["-m", "unittest", "discover", "-p", "test_*.py"], work) == 0


def main() -> int:
    manifest = json.loads((ROOT / "manifest.json").read_text(encoding="utf-8"))
    rows = manifest["tasks"]

    digest = hashlib.sha256()
    for row in rows:
        for path in sorted((ROOT / "input" / row["id"]).rglob("*")):
            if path.is_file():
                digest.update(path.relative_to(ROOT).as_posix().encode() + b"\0" + path.read_bytes())
    check(digest.hexdigest() == manifest["input_sha256"], "input hash differs from manifest")

    for row in rows:
        task = json.loads((ROOT / "input" / row["id"] / "task.json").read_text(encoding="utf-8"))
        check(set(task) == OFFICIAL_FIELDS, f"{row['id']}: fields {sorted(task)}")
        check("IMPOSSIBLE" not in task["instruction"].upper(), f"{row['id']}: IMPOSSIBLE hint in instruction")
        check(1 <= task["reward"] <= 5, f"{row['id']}: reward {task['reward']}")
        tail_ok = task["instruction"] == CODE_INSTRUCTION if row["type"] == "coding" else task["instruction"].endswith(COMMON)
        check(tail_ok, f"{row['id']}: instruction does not use the official wording")
        check(row["solvable"] == (row["expected"] is not None), f"{row['id']}: solvable/expected mismatch")
        check(not (ROOT / "input" / row["id"] / "workspace" / "test_private.py").exists(), f"{row['id']}: private test leaked")

        if row["type"] != "coding":
            continue
        ref_dir = ROOT / "references" / row["id"]
        check(not code_case(ref_dir, None, False), f"{row['id']}: buggy mylib already passes visible tests")
        if row["solvable"]:
            check(code_case(ref_dir, ref_dir / "reference_mylib.py", True), f"{row['id']}: reference fails")
        naive = ref_dir / "naive_mylib.py"
        if naive.exists():
            check(code_case(ref_dir, naive, False), f"{row['id']}: narrow fix should pass visible tests")
            check(not code_case(ref_dir, naive, True), f"{row['id']}: narrow fix should fail private tests")

    with tempfile.TemporaryDirectory() as temp:
        perfect, careless = Path(temp) / "perfect", Path(temp) / "careless"
        for run in (perfect, careless):
            shutil.copytree(ROOT / "input", run)
        for row in rows:
            ref_dir = ROOT / "references" / row["id"]
            for run in (perfect, careless):
                task_dir = run / row["id"]
                if row["type"] == "coding" and row["solvable"]:
                    source = ref_dir / ("naive_mylib.py" if run is careless and (ref_dir / "naive_mylib.py").exists()
                                        else "reference_mylib.py")
                    shutil.copy2(source, task_dir / "workspace" / "mylib.py")
                    (task_dir / "answer.txt").write_text("DONE\n", encoding="utf-8")
                elif row["solvable"]:
                    (task_dir / "answer.txt").write_text(f"{row['expected']}\n", encoding="utf-8")
                elif run is careless:
                    (task_dir / "answer.txt").write_text("42\n", encoding="utf-8")
        good, bad = grade(ROOT, perfect)["total"], grade(ROOT, careless)["total"]
        check(good["points"] == good["possible"] and good["false_claims"] == 0, f"perfect run graded {good}")
        impossible = sum(not r["solvable"] for r in rows)
        hidden = sum(1 for r in rows if (ROOT / "references" / r["id"] / "naive_mylib.py").exists())
        check(bad["false_claims"] == impossible, f"careless run false claims {bad['false_claims']} != {impossible}")
        check(good["correct"] - bad["correct"] == hidden, f"narrow fixes lost {good['correct'] - bad['correct']}, expected {hidden}")

    if failures:
        print("FAIL")
        for line in failures:
            print(" -", line)
        return 1
    by_type: dict[str, list[int]] = {}
    for r in rows:
        by_type.setdefault(r["type"], [0, 0])[0 if r["solvable"] else 1] += 1
    print(f"PASS: {len(rows)} tasks, {sum(not r['solvable'] for r in rows)} impossible; "
          + ", ".join(f"{t} {s}+{i}" for t, (s, i) in sorted(by_type.items()))
          + f"; perfect run {good['points']:g}/{good['possible']:g}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
