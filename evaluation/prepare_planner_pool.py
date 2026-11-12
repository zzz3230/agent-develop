"""Fresh random-reward workloads, with matching HOST-ONLY references for grading."""
import argparse
import hashlib
import json
from pathlib import Path
import random
import shutil


def prepare(pool,out,split,count,selection_seed,reward_seed):
    if out.exists():raise ValueError('Use a fresh output directory')
    if count<=0 or count%20:raise ValueError('Count must be positive and divisible by 20')
    rows=[]
    for s in ('train','eval') if split=='all' else (split,):
        rows+=json.loads((pool/s/'manifest.json').read_text(encoding='utf-8'))['tasks']
    rng=random.Random(selection_seed);reward_rng=random.Random(reward_seed);selected=[]
    for kind in ('math','data_analysis','search','coding'):
        for solvable,n in ((True,count//5),(False,count//20)):
            available=[r for r in rows if r['type']==kind and r['solvable']==solvable]
            selected+=rng.sample(available,n)
    rng.shuffle(selected);updated=[]
    for i,r in enumerate(selected):
        r=dict(r);r['reward']=reward_rng.randint(1,10);name=f'{i:04}_{r["id"]}'
        source=pool/r['split'];target=out/'input'/name
        shutil.copytree(source/'input'/r['id'],target)
        task=json.loads((target/'task.json').read_text(encoding='utf-8'));task['reward']=r['reward']
        (target/'task.json').write_bytes((json.dumps(task,ensure_ascii=False,indent=2)+'\n').encode('utf-8'))
        shutil.copytree(source/'references'/r['id'],out/'references'/r['id'])
        ref=out/'references'/r['id']/'task.json';raw=json.loads(ref.read_text(encoding='utf-8'));raw['reward']=r['reward']
        ref.write_bytes((json.dumps(raw,ensure_ascii=False,indent=2)+'\n').encode('utf-8'));updated.append(r)
    h=hashlib.sha256()
    for p in sorted((out/'input').rglob('*')):
        if p.is_file():h.update(p.relative_to(out/'input').as_posix().encode()+b'\0'+p.read_bytes())
    (out/'manifest.json').write_bytes((json.dumps(dict(selection_seed=selection_seed,reward_seed=reward_seed,
        split=split,input_sha256=h.hexdigest(),tasks=updated),ensure_ascii=False,indent=2)+'\n').encode('utf-8'))
    print(f'Prepared {count} tasks; mount ONLY {out / "input"}; hash {h.hexdigest()}')


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--pool',type=Path,default=Path('benchmarks/planner-500'));p.add_argument('--out',type=Path,required=True)
    p.add_argument('--split',choices=['train','eval','all'],default='eval');p.add_argument('--count',type=int,default=100)
    p.add_argument('--selection-seed',type=int,default=101);p.add_argument('--reward-seed',type=int,default=1001)
    a=p.parse_args();prepare(a.pool,a.out,a.split,a.count,a.selection_seed,a.reward_seed)
