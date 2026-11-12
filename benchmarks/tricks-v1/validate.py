"""Checks tricks-v1 without any model. Run from the repository root:

    python benchmarks/tricks-v1/validate.py --image hack:latest

Code tests import numpy, pandas and python-dateutil, so they run inside the given image.
"""
from __future__ import annotations

import argparse
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

import build  # noqa: E402
from evaluation.grade import grade  # noqa: E402

OFFICIAL_FIELDS = {"task_id", "task_type", "instruction", "reward", "check"}
failures: list[str] = []


def check(condition: bool, message: str) -> None:
    if not condition:
        failures.append(message)


def tests_pass(ref_dir: Path, mylib: Path | None, with_private: bool, image: str) -> bool:
    with tempfile.TemporaryDirectory(dir=REPO) as temp:   # inside the repo: Docker Desktop shares it
        work = Path(temp)
        shutil.copytree(ref_dir / "workspace", work, dirs_exist_ok=True)
        if mylib:
            shutil.copy2(mylib, work / "mylib.py")
        if with_private:
            shutil.copy2(ref_dir / "test_private.py", work / "test_private.py")
        done = subprocess.run(
            ["docker", "run", "--rm", "--network", "none", "--mount", f"type=bind,source={work},target=/w",
             "--workdir", "/w", "--entrypoint", "python", image, "-B", "-m", "unittest", "discover", "-p", "test_*.py"],
            capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=120)
        if done.returncode == 125:
            raise SystemExit(f"docker failed: {done.stderr.strip()[:300]}")
        return done.returncode == 0


def check_math_helpers() -> None:
    fib = [0, 1]
    for _ in range(200):
        fib.append(fib[-1] + fib[-2])
    check(all(build.fib_mod(n, 1_000_000_007) == fib[n] % 1_000_000_007 for n in range(150)), "fib_mod is wrong")
    check(all(build.divisor_summatory(n) == sum(n // k for k in range(1, n + 1)) for n in range(1, 400)),
          "divisor_summatory is wrong")
    check(build.basel_scaled() == 1644934, "Basel value is wrong")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--image", default="hack:latest")
    image = parser.parse_args().image

    check_math_helpers()
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
        check("IMPOSSIBLE" not in task["instruction"].upper(), f"{row['id']}: IMPOSSIBLE hint")
        check(row["solvable"] == (row["expected"] is not None), f"{row['id']}: solvable/expected mismatch")
        if row["type"] != "coding":
            continue
        ref_dir = ROOT / "references" / row["id"]
        check(not tests_pass(ref_dir, None, False, image), f"{row['id']}: buggy code already passes")
        check(tests_pass(ref_dir, ref_dir / "reference_mylib.py", True, image), f"{row['id']}: reference fails")
        naive = ref_dir / "naive_mylib.py"
        if naive.exists():
            check(tests_pass(ref_dir, naive, False, image), f"{row['id']}: narrow fix should pass visible tests")
            check(not tests_pass(ref_dir, naive, True, image), f"{row['id']}: narrow fix should fail private tests")

    with tempfile.TemporaryDirectory(dir=REPO) as temp:
        perfect, careless = Path(temp) / "perfect", Path(temp) / "careless"
        for run in (perfect, careless):
            shutil.copytree(ROOT / "input", run)
        for row in rows:
            ref_dir = ROOT / "references" / row["id"]
            for run in (perfect, careless):
                task_dir = run / row["id"]
                if row["type"] == "coding":
                    naive = ref_dir / "naive_mylib.py"
                    source = naive if run is careless and naive.exists() else ref_dir / "reference_mylib.py"
                    shutil.copy2(source, task_dir / "workspace" / "mylib.py")
                    (task_dir / "answer.txt").write_text("DONE\n", encoding="utf-8")
                elif row["solvable"]:
                    (task_dir / "answer.txt").write_text(f"{row['expected']}\n", encoding="utf-8")
                elif run is careless:
                    (task_dir / "answer.txt").write_text("42\n", encoding="utf-8")
        good = grade(ROOT, perfect, docker_image=image)["total"]
        bad = grade(ROOT, careless, docker_image=image)["total"]
        check(good["points"] == good["possible"] and good["false_claims"] == 0, f"perfect run graded {good}")
        impossible = sum(not r["solvable"] for r in rows)
        narrow = sum(1 for r in rows if (ROOT / "references" / r["id"] / "naive_mylib.py").exists())
        check(bad["false_claims"] == impossible, f"careless false claims {bad['false_claims']} != {impossible}")
        check(good["correct"] - bad["correct"] == narrow, f"narrow fixes lost {good['correct'] - bad['correct']} != {narrow}")

    if failures:
        print("FAIL")
        for line in failures:
            print(" -", line)
        return 1
    print(f"PASS: {len(rows)} tasks, {sum(not r['solvable'] for r in rows)} impossible; "
          f"perfect run {good['points']:g}/{good['possible']:g}; narrow code fixes lose {narrow} tasks")
    return 0


if __name__ == "__main__":
    sys.exit(main())
