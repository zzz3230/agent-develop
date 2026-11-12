"""Frozen protocol for offline scheduler experiments. All references remain host-only."""
import argparse
import importlib.util
import json
from pathlib import Path
import shutil
import random
import subprocess
import os

from evaluation.run_image import run

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'benchmark-runs'/'predictors-v1'
IMAGE='agent-develop:predictor-base'
TRAIN_SUITE=Path(os.environ.get('PREDICTOR_TRAIN_SUITE','C:/Users/hilis/hackathon-task/benchmark100-final'))


def dump(path,data):
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(data,ensure_ascii=False,indent=2),encoding='utf-8')


def diverse_module():
    spec=importlib.util.spec_from_file_location('diverse_suite',ROOT/'benchmarks/diverse-v1/suite.py')
    mod=importlib.util.module_from_spec(spec);spec.loader.exec_module(mod)
    return mod


def collect():
    OUT.mkdir(parents=True,exist_ok=True)
    old=TRAIN_SUITE
    if not (OUT/'train-diverse').exists():
        # prepare imports build by its local module name
        import sys
        sys.path.insert(0,str(ROOT/'benchmarks/diverse-v1'))
        diverse_module().prepare('dev',OUT/'train-diverse')
    datasets=[('train-old',old/'input',old),
              ('train-dev',OUT/'train-diverse/tasks',ROOT/'benchmarks/diverse-v1')]
    for label,tasks,refs in datasets:
        target=OUT/label
        if (target/'graded.json').exists(): continue
        run(IMAGE,tasks,target,env={'QUEUE':'0','RETRY':'0','ENFORCE_BUDGET':'0'},
            references=refs,with_probe=False,quiet=True)
        print('COLLECTED '+label,flush=True)


def control():
    import sys
    sys.path.insert(0,str(ROOT/'benchmarks/diverse-v1'))
    if not (OUT/'control-diverse').exists(): diverse_module().prepare('holdout',OUT/'control-diverse')
    if not (OUT/'control-v2').exists():
        from evaluation.build_suite import build_base
        build_base(OUT/'control-v2',20261111)
    target=OUT/'control'
    if target.exists(): return target
    target.mkdir(parents=True);rows=[]
    for root,inputs in [(ROOT/'benchmarks/diverse-v1',OUT/'control-diverse/tasks'),
                        (OUT/'control-v2/holdout',OUT/'control-v2/holdout/input')]:
        meta={r['id']:r for r in json.loads((root/'manifest.json').read_text(encoding='utf-8'))['tasks']}
        for folder in inputs.iterdir():
            if not (folder/'task.json').exists(): continue
            task_id=json.loads((folder/'task.json').read_text(encoding='utf-8'))['task_id']
            shutil.copytree(folder,target/'input'/task_id)
            shutil.copytree(root/'references'/task_id,target/'references'/task_id)
            rows.append(meta[task_id])
    dump(target/'manifest.json',dict(tasks=rows))
    return target


def compare():
    target=control();summary=[]
    for repeat,seed in enumerate([101,102,103]):
        inputs=OUT/f'control-order-{seed}'
        if not inputs.exists():
            folders=list(sorted((target/'input').iterdir()));random.Random(seed).shuffle(folders)
            for i,folder in enumerate(folders): shutil.copytree(folder,inputs/f'{i:03}_{folder.name}')
        modes=['baseline','numeric','embedding'];modes=modes[repeat:]+modes[:repeat]
        for mode in modes:
            label=f'{mode}-{seed}';out=OUT/label
            if not (out/'graded.json').exists():
                run('agent-develop:predictors',inputs,out,
                    env={'PREDICTOR':mode,'QUEUE':'1','RETRY':'0','BUDGET':'12000','ENFORCE_BUDGET':'1'},
                    hard_budget=12000,wall_limit=3600,references=target,with_probe=False,quiet=True)
            result=json.loads((out/'graded.json').read_text(encoding='utf-8'))
            run_info=json.loads((out/'run.json').read_text(encoding='utf-8'))
            summary.append(dict(mode=mode,seed=seed,points=result['total']['points'],correct=result['total']['correct'],
                                spent=result['spent'],seconds=run_info['wall_seconds'],run=str(out)))
            dump(OUT/'comparison.json',summary);print('COMPARED '+json.dumps(summary[-1]),flush=True)


def summarize():
    rows=json.loads((OUT/'comparison.json').read_text(encoding='utf-8'))
    result={}
    for mode in ('baseline','numeric','embedding'):
        selected=[r for r in rows if r['mode']==mode]
        if len(selected)!=3: raise ValueError('Expected three completed repetitions for '+mode)
        result[mode]={k:dict(mean=sum(r[k] or 0 for r in selected)/3,
                             minimum=min(r[k] or 0 for r in selected),maximum=max(r[k] or 0 for r in selected))
                      for k in ('points','correct','spent','seconds')}
    dump(OUT/'summary.json',result)
    print(json.dumps(result,indent=2))


def regrade():
    # Re-evaluate every variant by identical final rules, including interrupted code.
    from evaluation.grade import grade
    summary=[]
    for seed in (101,102,103):
        for mode in ('baseline','numeric','embedding'):
            out=OUT/f'{mode}-{seed}'
            old=json.loads((out/'graded.json').read_text(encoding='utf-8'))
            report=grade(OUT/'control',out/'tasks',out/'harness/trajectory.jsonl',docker_image='agent-develop:predictors')
            report['run']=old['run'];dump(out/'graded.json',report)
            info=json.loads((out/'run.json').read_text(encoding='utf-8'))
            info.update(total=report['total'],spent=report['spent']);dump(out/'run.json',info)
            summary.append(dict(mode=mode,seed=seed,points=report['total']['points'],correct=report['total']['correct'],
                spent=report['spent'],seconds=info['wall_seconds'],run=str(out)))
    dump(OUT/'comparison.json',summary);summarize()


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('command',choices=['collect','compare','summarize','regrade'])
    args=p.parse_args()
    if args.command=='collect': collect()
    elif args.command=='compare': compare()
    elif args.command=='regrade': regrade()
    else: summarize()
