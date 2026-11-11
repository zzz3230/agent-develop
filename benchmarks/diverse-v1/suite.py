"""Prepare clean agent inputs, validate fixtures, or grade completed task directories."""
from __future__ import annotations

import argparse
from collections import Counter
import json
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
import uuid

ROOT = Path(__file__).resolve().parent


def read(path):
    return json.loads(path.read_text(encoding='utf-8'))


def write(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')


def selected(split):
    return [r for r in read(ROOT/'manifest.json')['tasks']
            if split=='all' or (split=='smoke' and r['smoke']) or r['split']==split]


def verify_frozen():
    """Compare bytes and file lists, including references, against the reproducible source."""
    from build import artifacts
    expected=artifacts()
    for name,content in expected.items():
        if not (ROOT/name).is_file() or (ROOT/name).read_bytes()!=content.encode('utf-8'):
            raise ValueError('Missing or modified fixture: '+name)
    for folder in ('input','references'):
        actual={p.relative_to(ROOT).as_posix() for p in (ROOT/folder).rglob('*') if p.is_file()}
        wanted={p for p in expected if p.startswith(folder+'/')}
        if actual!=wanted:
            raise ValueError('Unexpected files in frozen suite: '+str(sorted(actual-wanted)))
    return expected


def validate():
    verify_frozen()
    rows=selected('all')
    assert len(rows)==64 and len({r['family'] for r in rows})==64
    assert Counter(r['type'] for r in rows)==dict.fromkeys(['math','data_analysis','search','coding'],16)
    assert len(selected('dev'))==40 and len(selected('holdout'))==24 and len(selected('smoke'))==12
    assert {r['id'] for r in selected('smoke')} <= {r['id'] for r in selected('dev')}
    assert not ({r['family'] for r in selected('dev')} & {r['family'] for r in selected('holdout')})
    total_tests=0
    for row in rows:
        task_id=row['id']; src=ROOT/'input'/task_id; ref=ROOT/'references'/task_id
        task=read(src/'task.json')
        assert set(task)=={'task_id','task_type','instruction','reward','check'}
        assert task['task_id']==task_id and task['task_type']==row['type']
        assert 'answer.txt' in task['instruction'] and not (src/'answer.txt').exists()
        assert not list(src.rglob('test_private*'))
        if task['check']!='unittest':
            if row['solvable'] and task['check']=='exact_int': int(read(ref/'answer.json')['expected'])
            continue
        # Only repository-authored fixtures execute locally. Agent submissions use Docker below.
        with tempfile.TemporaryDirectory(prefix='diverse-oracle-') as tmp:
            work=Path(tmp)
            shutil.copy2(src/'test_solution.py',work/'test_solution.py')
            shutil.copy2(ref/'test_private.py',work/'test_private.py')
            shutil.copy2(ref/'solution.py',work/'solution.py')
            result=subprocess.run([sys.executable,'-I','-B','-m','unittest','discover'],cwd=work,
                                  capture_output=True,text=True,encoding='utf-8',errors='replace',timeout=20)
            if result.returncode:
                raise AssertionError(task_id+' reference failed:\n'+result.stdout+result.stderr)
            found=re.search(r'Ran (\d+) tests?',result.stderr)
            total_tests+=int(found.group(1)) if found else 0
            shutil.copy2(src/'solution.py',work/'solution.py')
            result=subprocess.run([sys.executable,'-I','-B','-m','unittest','discover','-p','test_solution.py'],
                                  cwd=work,capture_output=True,text=True,encoding='utf-8',errors='replace',timeout=20)
            if result.returncode==0 or 'ModuleNotFoundError' in result.stderr or 'SyntaxError' in result.stderr:
                raise AssertionError(task_id+' baseline must fail a real behavioral test:\n'+result.stderr)
    print(f'PASS: 64 unique tasks; 16 correct code references; 16 buggy baselines fail; {total_tests} test methods.')
    print('Input SHA256: '+read(ROOT/'manifest.json')['input_sha256'])


def prepare(split, output, order_seed=None):
    verify_frozen()
    output=output.resolve()
    if output.exists():
        raise ValueError('Use a new, nonexistent directory for every run: '+str(output))
    if ROOT==output or ROOT in output.parents:
        raise ValueError('Run directories must be outside the frozen suite.')
    rows=selected(split)
    if order_seed is not None:
        import random
        random.Random(order_seed).shuffle(rows)
    output.mkdir(parents=True)
    exported=[]
    for i,row in enumerate(rows):
        # Directory ordering controls the existing runner. Canonical task_id stays unchanged.
        name=f'{i:03}_{row["id"]}' if order_seed is not None else row['id']
        shutil.copytree(ROOT/'input'/row['id'],output/'tasks'/name)
        exported.append(dict(id=row['id'],directory=name))
    write(output/'selection.json',dict(version='diverse-v1',split=split,
          input_sha256=read(ROOT/'manifest.json')['input_sha256'],order_seed=order_seed,tasks=exported))
    print(f'Prepared {len(rows)} tasks in {output / "tasks"}')
    print('Mount only this tasks directory into the agent container; selection.json stays outside.')


def code_judge(submission, original, reference, image):
    # Only the specified solution file is part of the coding contract. Never copy agent tests,
    # sitecustomize, caches, unrelated modules or symlinks into the judge.
    source=submission/'solution.py'
    if not source.is_file() or source.is_symlink() or source.stat().st_size>1_000_000:
        return False,'missing or oversized solution.py'
    for path in original.glob('test_*.py'):
        submitted=submission/path.name
        if submitted.is_symlink() or not submitted.is_file() or submitted.read_bytes()!=path.read_bytes():
            return False,'provided tests were edited or removed'
    with tempfile.TemporaryDirectory(prefix='diverse-judge-') as tmp:
        work=Path(tmp)
        shutil.copy2(source,work/'solution.py')
        shutil.copy2(original/'test_solution.py',work/'test_solution.py')
        shutil.copy2(reference/'test_private.py',work/'test_private.py')
        name='diverse-judge-'+uuid.uuid4().hex
        cmd=['docker','run','--rm','--name',name,'--pull','never','--network','none','--read-only',
             '--cap-drop','ALL','--security-opt','no-new-privileges','--cpus','1','--memory','256m',
             '--pids-limit','64','--tmpfs','/tmp:rw,size=16m','--mount',f'type=bind,source={work},target=/judge,readonly',
             '--workdir','/judge','--entrypoint','python',image,'-I','-B','-m','unittest','discover','-v']
        try:
            done=subprocess.run(cmd,capture_output=True,text=True,encoding='utf-8',errors='replace',timeout=35)
        except subprocess.TimeoutExpired:
            subprocess.run(['docker','rm','-f',name],capture_output=True,timeout=15)
            return False,'judge timeout (35 seconds)'
        detail=(done.stdout+done.stderr)[-5000:]
        if done.returncode in (125,126,127) or 'failed to connect to the docker' in detail.lower():
            raise RuntimeError('Judge infrastructure failed, no score recorded: '+detail)
        # Avoid counting a bare exit(0) as tests passed. This is an engineering benchmark,
        # not a hostile Python-code sandbox; documented below in README.
        success=done.returncode==0 and re.search(r'Ran [1-9]\d* tests?',detail) and re.search(r'\nOK\s*$',detail)
        return bool(success),detail


def grade(run, image, submissions=None, usage=None):
    verify_frozen()
    run=run.resolve()
    selection=read(run/'selection.json')
    manifest=read(ROOT/'manifest.json')
    if selection['input_sha256']!=manifest['input_sha256']:
        raise ValueError('Run refers to a different suite version.')
    refs={r['id']:r for r in manifest['tasks']}
    entries=selection['tasks']
    tasks=(submissions or run/'tasks').resolve()
    if ROOT==tasks or ROOT in tasks.parents:
        raise ValueError('Grade a run copy, not the frozen source tree.')
    judge_image_id=None
    if any(refs[e['id']]['check']=='unittest' for e in entries):
        # Fail before scoring rather than silently recording environment failures as wrong answers.
        result=subprocess.run(['docker','image','inspect',image],capture_output=True,text=True)
        if result.returncode: raise RuntimeError('Docker must be running and judge image must exist locally: '+image)
        judge_image_id=json.loads(result.stdout)[0]['Id']
    rows=[]
    for entry in entries:
        row=dict(refs[entry['id']]); task_id=row['id']; work=tasks/entry['directory']
        expected=read(ROOT/'references'/task_id/'answer.json')['expected']
        answer_path=work/'answer.txt'
        answer=answer_path.read_text(encoding='utf-8').strip() if answer_path.is_file() and not answer_path.is_symlink() and answer_path.stat().st_size<65536 else ''
        row.update(answer=answer,correct=False,points=0)
        row['attempted']=answer_path.is_file() or (row['type']=='coding' and (work/'solution.py').is_file()
                           and (work/'solution.py').read_bytes()!=(ROOT/'input'/task_id/'solution.py').read_bytes())
        if not row['solvable']:
            row['abstained']=not answer or answer.upper()=='IMPOSSIBLE'
        elif row['check']=='unittest':
            if answer=='DONE':
                row['correct'],row['judge_detail']=code_judge(work,ROOT/'input'/task_id,ROOT/'references'/task_id,image)
        elif row['check']=='exact_int':
            row['correct']=bool(re.fullmatch(r'[+-]?\d+',answer)) and int(answer)==int(expected)
        else:
            # Explicit local normalization; organizers have not frozen their exact normalizer.
            row['correct']=' '.join(answer.split()).casefold()==' '.join(expected.split()).casefold()
        row['points']=row['reward'] if row['correct'] else 0
        rows.append(row)
    def stats(items):
        return dict(total=len(items),solvable=sum(r['solvable'] for r in items),
                    correct=sum(r['correct'] for r in items),points=sum(r['points'] for r in items),
                    possible_points=sum(r['reward'] for r in items if r['solvable']),
                    unavailable=sum(not r['solvable'] for r in items),
                    abstentions_on_unavailable=sum(r.get('abstained',False) for r in items))
    result=dict(version=manifest['version'],input_sha256=manifest['input_sha256'],selection=selection,
                judge_image=image,judge_image_id=judge_image_id,
                total=stats(rows),by_type={k:stats([r for r in rows if r['type']==k]) for k in sorted({r['type'] for r in rows})},
                by_difficulty={k:stats([r for r in rows if r['difficulty']==k]) for k in ['easy','medium','hard']},rows=rows)
    if usage:
        # All calls, including interrupted/unanswered tasks. Never infer cost from completed answers.
        inp=out=calls=estimated=0
        with usage.open(encoding='utf-8') as stream:
            for line in stream:
                if not line.strip(): continue
                e=json.loads(line)
                if e.get('event')=='llm_call':
                    inp+=int(e['input']); out+=int(e['output']); calls+=1; estimated+=bool(e.get('estimated'))
        result['usage']=dict(input_tokens=inp,output_tokens=out,calls=calls,estimated_calls=estimated,
                             weighted_tokens=round(inp/10+out,1),source=str(usage.resolve()))
    else:
        result['usage']=None
    write(run/'graded.json',result)
    print(json.dumps({k:v for k,v in result.items() if k not in ('rows','selection')},ensure_ascii=False,indent=2))
    print('Saved '+str(run/'graded.json'))
    return result


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    sub=parser.add_subparsers(dest='command',required=True)
    sub.add_parser('validate',help='Offline fixture checks; no Docker or LLM needed')
    p=sub.add_parser('prepare',help='Export clean writable inputs to a new run directory')
    p.add_argument('--split',choices=['smoke','dev','holdout','all'],default='smoke')
    p.add_argument('--out',required=True,type=Path)
    p.add_argument('--order-seed',type=int,help='Shuffle directory order reproducibly; use the same seed for both agents')
    p=sub.add_parser('grade',help='Grade in-place contest answers or compare_stock output copies')
    p.add_argument('--run',required=True,type=Path,help='Directory containing selection.json')
    p.add_argument('--submissions',type=Path,help='Override the default RUN/tasks with completed task directories')
    p.add_argument('--image',default='hack:latest',help='Locally available Python image; no downloads')
    p.add_argument('--usage',type=Path,help='Optional agent Journal JSONL; all charged calls count')
    args=parser.parse_args()
    try:
        if args.command=='validate': validate()
        elif args.command=='prepare': prepare(args.split,args.out,args.order_seed)
        else: grade(args.run,args.image,args.submissions,args.usage)
    except (ValueError,AssertionError,RuntimeError,OSError,subprocess.SubprocessError) as exc:
        parser.exit(1,str(exc)+'\n')


if __name__=='__main__': main()
