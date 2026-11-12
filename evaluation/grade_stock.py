"""Host-side grading of compare_stock outputs; references never enter agent containers."""
from __future__ import annotations
import argparse
from collections import Counter
import json
from pathlib import Path
import shutil
import subprocess
import tempfile


def grade(root, variant, image, run_directory=None):
    manifest = json.loads((root/'manifest.json').read_text(encoding='utf-8'))
    run = run_directory or root/variant
    rows = [json.loads(x) for x in (run/'results.jsonl').read_text(encoding='utf-8').splitlines()]
    refs = {r['id']: r for r in manifest['tasks']}
    events = [json.loads(x) for x in (run/'usage.jsonl').read_text(encoding='utf-8').splitlines()]
    withdrawn = [r for r in rows if r['id'] not in refs]
    rows = [r for r in rows if r['id'] in refs]
    graded = []
    for result in rows:
        ref = refs[result['id']]
        row = {**result, 'solvable': ref['solvable'], 'expected': ref['expected'], 'correct': False}
        if not ref['solvable']:
            row['recognized_impossible'] = result['status'] == 'impossible'
        elif ref['check'] == 'unittest':
            with tempfile.TemporaryDirectory(prefix='oj100-judge-') as temporary:
                work = Path(temporary)
                source = run/'tasks'/ref['id']/'workspace'
                shutil.copytree(source, work, dirs_exist_ok=True)
                original = root/'references'/ref['id']
                shutil.copy2(original/'workspace'/'test_solution.py', work/'test_solution.py')
                shutil.copy2(original/'test_private.py', work/'test_private.py')
                try:
                    done = subprocess.run(['docker','run','--rm','--network','none','--read-only',
                        '--cap-drop','ALL','--security-opt','no-new-privileges','--cpus','1','--memory','512m',
                        '--pids-limit','64','--tmpfs','/tmp:rw,size=32m','--mount',f'type=bind,source={work},target=/judge,readonly',
                        '--workdir','/judge','--entrypoint','python',image,'-B','-m','unittest','discover'],
                        capture_output=True,text=True,timeout=40)
                    row['private_pass'] = done.returncode == 0
                    row['private_detail'] = (done.stdout+done.stderr)[-3500:]
                except subprocess.TimeoutExpired:
                    row['private_pass'] = False
                    row['private_detail'] = 'judge timeout'
            row['correct'] = result['status'] == 'solved' and result['answer'] == 'DONE' and row['private_pass']
        elif result['status'] == 'solved':
            if ref['check'] == 'exact_int':
                try:
                    row['correct'] = int(result['answer']) == int(ref['expected'])
                except ValueError:
                    pass
            else:
                row['correct'] = result['answer'] == str(ref['expected'])
        calls = [e for e in events if e.get('event') == 'llm_call' and e.get('task') == ref['id']]
        row['input'] = sum(e['input'] for e in calls)
        row['output'] = sum(e['output'] for e in calls)
        row['calls'] = len(calls)
        row['estimated_calls'] = sum(bool(e.get('estimated')) for e in calls)
        graded.append(row)
    def stats(selected):
        return dict(attempted=len(selected), solved=sum(r['correct'] for r in selected),
            solvable_attempted=sum(r['solvable'] for r in selected),
            impossible_attempted=sum(not r['solvable'] for r in selected),
            points=sum(r['reward'] for r in selected if r['correct']),
            cost=round(sum(r['cost'] for r in selected),1), input=sum(r['input'] for r in selected),
            output=sum(r['output'] for r in selected), calls=sum(r['calls'] for r in selected),
            seconds=round(sum(r['seconds'] for r in selected),1),
            impossible_recognized=sum(r.get('recognized_impossible',False) for r in selected),
            impossible_false_claims=sum(not r['solvable'] and r['status']=='solved' for r in selected),
            infrastructure_retries=sum(max(0,len(r.get('attempts',[]))-1) for r in selected),
            estimated_calls=sum(r['estimated_calls'] for r in selected))
    prefix=[]; spent=0
    for row in graded:
        spent += row['cost']
        if spent > 100000:
            break
        prefix.append(row)
    report = dict(variant=variant, input_sha256=manifest['input_sha256'], total=stats(graded),
        configuration=json.loads((run/'config.json').read_text(encoding='utf-8')) if (run/'config.json').exists() else None,
        requested=len(refs), unattempted=sorted(set(refs)-{r['id'] for r in rows}),
        finish=next((e for e in reversed(events) if e.get('event')=='benchmark_finish'),None),
        withdrawn_attempts=len(withdrawn), withdrawn_cost=round(sum(r['cost'] for r in withdrawn),1),
        withdrawn_seconds=round(sum(r['seconds'] for r in withdrawn),1),
        raw_measured_cost=round(sum(r['cost'] for r in rows+withdrawn),1),
        stop_reasons=dict(Counter(e.get('reason') for e in events
            if e.get('event')=='attempt_stop' and e.get('task') in refs)),
        possible_points=sum(r['reward'] for r in manifest['tasks'] if r['solvable']),
        by_type={kind:stats([r for r in graded if r['type']==kind]) for kind in sorted({r['type'] for r in graded})},
        prefix_100k=stats(prefix), rows=graded)
    (run/'graded.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps({k:v for k,v in report.items() if k!='rows'},ensure_ascii=False,indent=2))
    return report


if __name__ == '__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--root',type=Path,required=True)
    p.add_argument('--variant',choices=['stock','ours'],required=True)
    p.add_argument('--image',default='agent-develop:stock-comparison')
    p.add_argument('--run-dir',type=Path)
    args=p.parse_args()
    grade(args.root,args.variant,args.image,args.run_dir)
