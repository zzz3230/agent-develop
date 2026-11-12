"""Contest grader: one command, per-task correctness, reward, cost, time and the total.

    python -m evaluation.grade --references REF --run TASKS [--trajectory T] [--json OUT] [--docker IMAGE]

REF is any of the reference layouts used in this repository, detected automatically:
  * benchmarks/diverse-v1 (manifest.json + references/<id>/answer.json, input/<id>);
  * a build_suite split (manifest.json + references/<id>/task.json with expected);
  * a directory of task folders whose task.json carries `expected` (official examples,
    evaluation/fixtures/tasks; add --private evaluation/fixtures/private_checks).
TASKS is the directory the agent worked on; tasks are matched by task.json task_id, so
shuffled or prefixed folder names are fine. References never have to be inside TASKS.

Answers are compared only by the rule named in each task's `check`:
  exact_int    the answer, without surrounding whitespace, is one integer equal to expected;
  exact_str    surrounding whitespace removed and case ignored, the organisers' stated rule;
               nothing else (no inner-space collapsing, no punctuation stripping);
  unittest     the original visible tests plus private tests pass on a copy of the agent's
               code, with the original test files put back; edited tests count as failure;
  unavailable  never earns points; any answer other than IMPOSSIBLE is a false claim.
The journal's "solved" status is reported next to the verdict but never used as proof.
Metrics subclass openJiuwen's evaluator Metric when the package is installed.
"""
from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import sys
import tempfile
import uuid
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

try:  # reuse the OJ metric interface where available; the grader itself needs only stdlib
    from openjiuwen.agent_evolving.evaluator.metrics.base import Metric
except Exception:  # pragma: no cover - host without openjiuwen
    class Metric:  # type: ignore[no-redef]
        pass

SKIP_COPY = {'answer.txt', '.answer.tmp', 'task.json', '__pycache__'}


# ---------- metrics -------------------------------------------------------------------------

class ExactIntMetric(Metric):
    name = 'exact_int'

    def compute(self, prediction, label, **kwargs) -> float:
        text = (prediction or '').strip()
        return float(bool(re.fullmatch(r'[+-]?\d+', text)) and int(text) == int(str(label).strip()))


class ExactStrMetric(Metric):
    name = 'exact_str'

    def compute(self, prediction, label, **kwargs) -> float:
        return float((prediction or '').strip().casefold() == str(label).strip().casefold())


METRICS = {'exact_int': ExactIntMetric(), 'exact_str': ExactStrMetric()}


# ---------- references ----------------------------------------------------------------------

@dataclass
class Ref:
    id: str
    type: str
    reward: float
    check: str
    expected: Optional[str]
    solvable: bool
    original: Optional[Path] = None          # folder with the original test_*.py
    private: list = field(default_factory=list)
    contract: Optional[list] = None          # only these files are taken from the agent


def _json(path: Path):
    return json.loads(path.read_text(encoding='utf-8'))


def load_references(root: Path, private_dir: Optional[Path] = None) -> list[Ref]:
    manifest = root / 'manifest.json'
    if manifest.is_file() and (root / 'references').is_dir():
        data = _json(manifest)
        refs = []
        for row in data['tasks']:
            ref_dir = root / 'references' / row['id']
            if (ref_dir / 'answer.json').is_file():          # benchmarks/diverse-v1
                expected = _json(ref_dir / 'answer.json').get('expected')
                original, contract = root / 'input' / row['id'], ['solution.py']
            else:                                            # evaluation/build_suite
                expected = row.get('expected')
                original, contract = ref_dir / 'workspace', None
            private = [p for p in [ref_dir / 'test_private.py'] if p.is_file()]
            check = row['check'] if row.get('solvable', True) else 'unavailable'
            refs.append(Ref(row['id'], row['type'], float(row['reward']), check,
                            None if expected is None else str(expected), bool(row.get('solvable', True)),
                            original, private, contract))
        return refs
    refs = []
    for task_json in sorted(root.glob('*/task.json')):      # official examples, fixtures
        raw = _json(task_json)
        task_id = str(raw.get('task_id') or task_json.parent.name)
        check = raw.get('check', '')
        if 'expected' not in raw and check != 'unavailable':
            raise ValueError(f'{task_json}: no expected answer; this is an agent input, not a reference')
        workspace = task_json.parent / 'workspace'
        private = []
        if private_dir and (private_dir / f'{task_id}.py').is_file():
            private.append(private_dir / f'{task_id}.py')
        refs.append(Ref(task_id, raw['task_type'], float(raw.get('reward', 0)), check,
                        None if raw.get('expected') is None else str(raw['expected']), check != 'unavailable',
                        workspace if workspace.is_dir() else task_json.parent, private))
    if not refs:
        raise ValueError(f'{root}: no references found')
    return refs


# ---------- run directory and journal -------------------------------------------------------

def index_run(run: Path) -> dict[str, Path]:
    found = {}
    for task_json in run.glob('*/task.json'):
        try:
            task_id = str(_json(task_json).get('task_id') or task_json.parent.name)
        except (OSError, ValueError):
            task_id = task_json.parent.name
        found[task_id] = task_json.parent
    return found


def read_journal(path: Optional[Path]):
    cost, seconds, status, started = defaultdict(float), defaultdict(float), {}, {}
    total, finish = 0.0, {}
    if not path or not path.is_file():
        return None
    for line in path.read_text(encoding='utf-8', errors='replace').splitlines():
        try:
            event = json.loads(line)
        except ValueError:
            continue
        kind = event.get('event')
        if kind == 'llm_call':
            charge = float(event.get('cost', int(event.get('input', 0)) / 10 + int(event.get('output', 0))))
            total += charge
            if event.get('task'):
                cost[event['task']] += charge
        elif kind == 'attempt_start':
            started[event['task']] = event['t']
        elif kind == 'outcome':
            status[event['task']] = event.get('status')
            if event['task'] in started:
                seconds[event['task']] += event['t'] - started.pop(event['task'])
        elif kind == 'finish':
            finish = event
    return dict(cost=cost, seconds=seconds, status=status, total=total, finish=finish)


# ---------- unittest judge ------------------------------------------------------------------

def run_tests(work: Path, docker_image: Optional[str]) -> tuple[bool, str]:
    if docker_image:
        name = 'grade-' + uuid.uuid4().hex[:12]
        command = ['docker', 'run', '--rm', '--name', name, '--pull', 'never', '--network', 'none',
                   '--read-only', '--cap-drop', 'ALL', '--security-opt', 'no-new-privileges',
                   '--cpus', '1', '--memory', '512m', '--pids-limit', '64', '--tmpfs', '/tmp:rw,size=32m',
                   '--mount', f'type=bind,source={work},target=/judge,readonly', '--workdir', '/judge',
                   '--entrypoint', 'python', docker_image, '-I', '-B', '-m', 'unittest', 'discover', '-v']
    else:
        name, command = None, [sys.executable, '-I', '-B', '-m', 'unittest', 'discover', '-v']
    try:
        done = subprocess.run(command, cwd=work, capture_output=True, text=True, encoding='utf-8',
                              errors='replace', timeout=60, stdin=subprocess.DEVNULL)
    except subprocess.TimeoutExpired:
        if name:
            subprocess.run(['docker', 'rm', '-f', name], capture_output=True)
        return False, 'tests timed out (60 s)'
    detail = (done.stdout + done.stderr)[-3000:]
    if docker_image and done.returncode in (125, 126, 127):
        raise RuntimeError('judge container failed to start, nothing graded: ' + detail[-500:])
    ran = re.search(r'Ran ([1-9]\d*) tests?', detail)
    return bool(done.returncode == 0 and ran and re.search(r'\nOK\b', detail)), detail


def judge_code(ref: Ref, workdir: Path, docker_image: Optional[str]) -> tuple[bool, str]:
    originals = sorted(ref.original.glob('test_*.py')) if ref.original else []
    for test in originals:
        submitted = workdir / test.name
        if not submitted.is_file() or submitted.read_bytes() != test.read_bytes():
            return False, f'original test {test.name} was edited or removed'
    with tempfile.TemporaryDirectory(prefix='contest-judge-') as temp:
        work = Path(temp)
        if ref.contract:
            for name in ref.contract:
                source = workdir / name
                if not source.is_file() or source.is_symlink():
                    return False, f'missing {name}'
                shutil.copy2(source, work / name)
        else:
            for item in workdir.iterdir():
                if item.name in SKIP_COPY or item.name.startswith('test_') or item.is_symlink():
                    continue
                (shutil.copytree if item.is_dir() else shutil.copy2)(item, work / item.name)
        for test in originals:
            shutil.copy2(test, work / test.name)
        for number, private in enumerate(ref.private):
            shutil.copy2(private, work / f'test_private_{number}.py')
        return run_tests(work, docker_image)


# ---------- grading -------------------------------------------------------------------------

def grade(references: Path, run: Path, trajectory: Optional[Path] = None, private_dir: Optional[Path] = None,
          docker_image: Optional[str] = None) -> dict:
    refs = load_references(references, private_dir)
    folders = index_run(run)
    journal = read_journal(trajectory)
    rows, not_in_run = [], []
    for ref in refs:
        folder = folders.get(ref.id)
        row = dict(id=ref.id, type=ref.type, reward=ref.reward, check=ref.check, solvable=ref.solvable,
                   answer=None, correct=False, points=0.0, note='')
        if journal:
            row.update(journal_status=journal['status'].get(ref.id, 'not_run'),
                       cost=round(journal['cost'].get(ref.id, 0.0), 1),
                       seconds=round(journal['seconds'].get(ref.id, 0.0), 1))
        if folder is None:
            not_in_run.append(ref.id)
            continue
        answer_path = folder / 'answer.txt'
        if answer_path.is_file() and not answer_path.is_symlink() and answer_path.stat().st_size < 65536:
            row['answer'] = answer_path.read_text(encoding='utf-8', errors='replace').strip()
        workdir = folder / 'workspace' if (folder / 'workspace').is_dir() else folder
        if not ref.solvable:
            row['false_claim'] = row['answer'] not in (None, '') and row['answer'].upper() != 'IMPOSSIBLE'
            row['note'] = 'answered on unavailable data' if row['false_claim'] else 'no answer, correct abstention'
        elif ref.check == 'unittest':
            if row['answer'] != 'DONE':
                row['note'] = 'missing DONE answer.txt'
            else:
                row['correct'], detail = judge_code(ref, workdir, docker_image)
                row['note'] = 'tests pass' if row['correct'] else detail.strip().splitlines()[-1][:160] if detail.strip() else 'tests fail'
        elif ref.check in METRICS:
            if row['answer'] is None:
                row['note'] = 'no answer.txt'
            else:
                row['correct'] = METRICS[ref.check].compute(row['answer'], ref.expected) == 1.0
                if not row['correct']:
                    row['note'] = f'expected {ref.expected!r}'
        else:
            row['note'] = f'unknown check {ref.check!r}'
        row['points'] = ref.reward if row['correct'] else 0.0
        if journal and row.get('journal_status') == 'solved' and not row['correct']:
            row['note'] = ('journal says solved; ' + row['note']).strip('; ')
        rows.append(row)

    def stats(selected):
        out = dict(tasks=len(selected), solvable=sum(r['solvable'] for r in selected),
                   correct=sum(r['correct'] for r in selected), points=sum(r['points'] for r in selected),
                   possible=sum(r['reward'] for r in selected if r['solvable']),
                   false_claims=sum(r.get('false_claim', False) for r in selected))
        if journal:
            out['cost'] = round(sum(r.get('cost', 0) for r in selected), 1)
            out['journal_solved_but_wrong'] = sum(r.get('journal_status') == 'solved' and r['solvable']
                                                  and not r['correct'] for r in selected)
        return out

    report = dict(references=str(references), run=str(run), total=stats(rows),
                  by_type={k: stats([r for r in rows if r['type'] == k]) for k in sorted({r['type'] for r in rows})},
                  rows=rows)
    if journal:
        report['spent'] = round(journal['total'], 1)          # every charged call, incl. interrupted tasks
        report['seconds'] = journal['finish'].get('seconds')
        report['stop'] = journal['finish'].get('stop')
    report['references_not_in_run'] = len(not_in_run)   # e.g. other splits; never scored
    extra = sorted(set(folders) - {r.id for r in refs})
    if extra:
        report['unreferenced_tasks'] = extra
    return report


def print_report(report: dict) -> None:
    has_cost = 'spent' in report
    head = '| Задача | Тип | Reward | Верно | Баллы |' + (' Журнал | Расход | Время, с |' if has_cost else '') + ' Примечание |'
    print(head)
    print('|' + '---|' * (head.count('|') - 1))
    for r in report['rows']:
        cells = [r['id'], r['type'], f"{r['reward']:g}", 'да' if r['correct'] else ('—' if not r['solvable'] else 'нет'),
                 f"{r['points']:g}"]
        if has_cost:
            cells += [r.get('journal_status', ''), f"{r.get('cost', 0):g}", f"{r.get('seconds', 0):g}"]
        cells.append(r['note'].replace('|', '/'))
        print('| ' + ' | '.join(cells) + ' |')
    t = report['total']
    line = (f"\nИтого: {t['points']:g} из {t['possible']:g} баллов, верно {t['correct']} из {t['solvable']} "
            f"выполнимых, ложных ответов на невыполнимые {t['false_claims']}")
    if has_cost:
        line += (f"; расход {report['spent']} (по задачам {t['cost']}), время {report['seconds']} с, "
                 f"остановка: {report['stop']}; «solved» в журнале, но неверно: {t['journal_solved_but_wrong']}")
    print(line)
    if report.get('unreferenced_tasks'):
        print('Задачи без эталона (не оценены): ' + ', '.join(report['unreferenced_tasks']))


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--references', type=Path, required=True)
    parser.add_argument('--run', type=Path, required=True, help='task directories the agent worked on')
    parser.add_argument('--trajectory', type=Path, help='run journal (trajectory.jsonl) for cost and time')
    parser.add_argument('--private', type=Path, help='extra private tests named <task_id>.py')
    parser.add_argument('--docker', metavar='IMAGE', help='run code tests in this local image, no network')
    parser.add_argument('--json', type=Path, help='save the full report')
    args = parser.parse_args(argv)
    report = grade(args.references, args.run, args.trajectory, args.private, args.docker)
    if args.json:
        args.json.parent.mkdir(parents=True, exist_ok=True)
        args.json.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    print_report(report)
    return 0


if __name__ == '__main__':
    sys.exit(main())
