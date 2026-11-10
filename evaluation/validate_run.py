"""Host-side validation of a run against offline references; never used by the agent."""
from __future__ import annotations

import argparse
import json
import shutil
import tempfile
from pathlib import Path

from evaluation.check_examples import check_coding


def validate(run: Path, references: Path, private: Path, image: str) -> dict:
    events = [json.loads(line) for line in (run/'logs'/'trajectory.jsonl').read_text(encoding='utf-8').splitlines()]
    outcomes = {e['task']: e for e in events if e.get('event') == 'outcome'}
    rows = []
    for directory in sorted((run/'tasks').iterdir()):
        source = references/directory.name
        spec = json.loads((source/'task.json').read_text(encoding='utf-8'))
        answer_path = directory/'answer.txt'
        answer = answer_path.read_text(encoding='utf-8').strip() if answer_path.exists() else None
        outcome = outcomes.get(spec['task_id'])
        detail = str((outcome or {}).get('detail', ''))
        row = dict(task=spec['task_id'], type=spec['task_type'], check=spec['check'],
                   answer=answer, correct=False, reward=spec['reward'], outcome=outcome,
                   infrastructure_failure='model call failed' in detail and any(code in detail for code in ('429','500','502','503','504')),
                   group='control' if directory.name.startswith('control_') else 'development' if directory.name.startswith('hard_') else 'official')
        if spec['check'] == 'unavailable':
            row['correct'] = answer is None
        elif spec['check'] == 'unittest':
            result = check_coding(source/'workspace', directory/'workspace', image)
            row.update(result)
            row['correct'] = answer == 'DONE' and result['tests_pass'] and not result['tests_changed'] and (outcome or {}).get('status') == 'solved'
            hidden = private/(directory.name+'.py')
            if hidden.exists():
                with tempfile.TemporaryDirectory(prefix='private-check-') as temp:
                    work = Path(temp)/'workspace'
                    shutil.copytree(directory/'workspace', work)
                    shutil.copy2(hidden, work/'test_private.py')
                    checked = check_coding(source/'workspace', work, image)
                row['private_tests_pass'] = checked['tests_pass']
                row['private_detail'] = checked['test_detail']
                row['correct'] = row['correct'] and checked['tests_pass']
        elif spec['check'] == 'exact_int':
            try:
                row['correct'] = answer is not None and int(answer) == int(spec['expected'])
            except ValueError:
                pass
        else:
            row['correct'] = answer == spec['expected']
        calls = [e for e in events if e.get('event') == 'llm_call' and e.get('task') == spec['task_id']]
        row['cost'] = round(sum(e['cost'] for e in calls), 1)
        row['calls'] = len(calls)
        rows.append(row)
    return dict(run=str(run), rows=rows,
                finish=next((e for e in reversed(events) if e.get('event') == 'finish'), None))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    fixtures = Path(__file__).parent/'fixtures'
    parser.add_argument('--run', required=True, type=Path)
    parser.add_argument('--references', type=Path, default=fixtures/'tasks')
    parser.add_argument('--private-tests', type=Path, default=fixtures/'private_checks')
    parser.add_argument('--image', default='agent-develop:m2-limits-final')
    args = parser.parse_args()
    report = validate(args.run, args.references, args.private_tests, args.image)
    (args.run/'issue-graded.json').write_text(json.dumps(report, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
    for group in ('official', 'development', 'control'):
        selected = [r for r in report['rows'] if r['group'] == group and r['check'] != 'unavailable']
        print(group, f"{sum(r['correct'] for r in selected)}/{len(selected)}")
    for row in report['rows']:
        if not row['correct']:
            print('FAIL', row['task'], row['answer'], 'API failure' if row['infrastructure_failure'] else row['outcome'])
    print(report['finish'])
    return 0 if all(row['correct'] for row in report['rows']) else 1


if __name__ == '__main__':
    raise SystemExit(main())
