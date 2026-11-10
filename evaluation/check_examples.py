"""Independently check a saved example run; never send reference answers to the agent."""
from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import tempfile
from pathlib import Path


def check_coding(source: Path, candidate: Path, image: str) -> dict:
    tests = sorted(source.rglob('test_*.py'))
    changed = [str(p.relative_to(source)) for p in tests
               if not (candidate / p.relative_to(source)).is_file()
               or p.read_bytes() != (candidate / p.relative_to(source)).read_bytes()]
    if not tests:
        return {'tests_pass': False, 'tests_changed': changed, 'test_detail': 'No original tests'}
    # Run candidate code against original tests in a disposable, offline container.
    with tempfile.TemporaryDirectory(prefix='oj-check-') as temp:
        work = Path(temp) / 'workspace'
        shutil.copytree(candidate, work)
        for test in tests:
            dest = work / test.relative_to(source)
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(test, dest)
        command = ['docker', 'run', '--rm', '--network', 'none', '--read-only',
                   '--tmpfs', '/tmp:rw,size=128m', '--cap-drop', 'ALL',
                   '--security-opt', 'no-new-privileges', '--memory', '512m',
                   '--cpus', '1', '--pids-limit', '64',
                   '--mount', f'type=bind,source={work},target=/work,readonly',
                   '--workdir', '/work', '--entrypoint', 'timeout', image,
                   '20', 'python', '-B', '-m', 'unittest', 'discover', '-s', '.', '-p', 'test_*.py']
        result = subprocess.run(command, capture_output=True, text=True, encoding='utf-8', errors='replace')
    output = result.stdout + result.stderr
    ran = re.search(r'Ran (\d+) tests?', output)
    return {'tests_pass': result.returncode == 0 and bool(ran and int(ran[1]) > 0),
            'tests_changed': changed, 'test_detail': output[-4000:]}


def evaluate(source: Path, run: Path, image: str) -> dict:
    journal = run / 'logs' / 'trajectory.jsonl'
    events = [json.loads(line) for line in journal.read_text(encoding='utf-8').splitlines() if line.strip()]
    outcomes = {e['task']: e for e in events if e.get('event') == 'outcome'}
    rows = []
    for task_file in sorted(source.glob('*/task.json')):
        task = json.loads(task_file.read_text(encoding='utf-8'))
        task_id = task['task_id']
        directory = run / 'tasks' / task_file.parent.name
        answer_file = directory / 'answer.txt'
        answer = answer_file.read_text(encoding='utf-8').strip() if answer_file.is_file() else None
        calls = [e for e in events if e.get('event') == 'llm_call' and e.get('task') == task_id]
        row = {'task': task_id, 'type': task['task_type'], 'answer': answer,
               'expected': task['expected'], 'correct': False, 'reward': task['reward'],
               'calls': len(calls), 'cost': round(sum(e['cost'] for e in calls), 3),
               'outcome': outcomes.get(task_id), 'attempted': directory.is_dir()}
        if task['check'] == 'unittest' and directory.is_dir():
            row.update(check_coding(task_file.parent / 'workspace', directory / 'workspace', image))
            row['correct'] = answer == 'DONE' and row['tests_pass'] and not row['tests_changed']
        elif task['check'] == 'exact_int':
            row['correct'] = bool(answer is not None and re.fullmatch(r'[+-]?\d+', answer)
                                  and int(answer) == int(task['expected']))
        elif task['check'] == 'exact_str':
            row['correct'] = answer == task['expected']
        if not row['attempted']:
            row['verdict'] = 'not_run'
        elif row['correct']:
            row['verdict'] = 'pass'
        elif row.get('tests_changed'):
            row['verdict'] = 'tests_modified'
        elif answer is None:
            row['verdict'] = 'missing_answer'
        elif task['check'] == 'unittest' and not row.get('tests_pass'):
            row['verdict'] = 'tests_failed'
        else:
            row['verdict'] = 'wrong_answer'
        row['points'] = task['reward'] if row['correct'] else 0
        rows.append(row)
    return {'run': str(run.resolve()), 'image': image, 'tasks': rows,
            'points': sum(r['points'] for r in rows), 'max_points': sum(r['reward'] for r in rows),
            'correct': sum(r['correct'] for r in rows),
            'finish': next((e for e in reversed(events) if e.get('event') == 'finish'), None)}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', required=True, type=Path, help='Original examples with references')
    parser.add_argument('--run', required=True, type=Path, help='Saved run containing tasks/ and logs/')
    parser.add_argument('--image', default='agent-develop:c789e74')
    parser.add_argument('--output', required=True, type=Path)
    args = parser.parse_args()
    report = evaluate(args.source, args.run, args.image)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    for row in report['tasks']:
        print(f"{row['task']}: {row['verdict']} answer={row['answer']!r} cost={row['cost']}")
    print(f"Correct: {report['correct']}/{len(report['tasks'])}; points: {report['points']}/{report['max_points']}")
    return 0 if all(r['correct'] for r in report['tasks']) else 1


if __name__ == '__main__':
    raise SystemExit(main())
