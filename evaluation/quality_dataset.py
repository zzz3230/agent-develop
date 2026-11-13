"""Freeze quality-only families, compatible labels and an independent workload."""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import random
import shutil

from evaluation.build_planner_pool import sources,cases,payload,adapt,write

ROOT=Path(__file__).resolve().parents[1]
META=ROOT/'benchmarks/quality-minilm'
WORK=ROOT/'benchmark-runs/quality-minilm-v1'
SEED=20261114
KINDS=('math','data_analysis','search','coding')
ALIASES={
    'diverse:math:business_calendar':'business_calendar',
    'tricks:coding:coding_0000':'business_calendar',
    'diverse:coding:rational_decimal':'decimal_rounding',
    'tricks:coding:coding_0002':'decimal_rounding',
    'gaps:math:math_0007':'decimal_rounding',
    'diverse:coding:stable_unique':'stable_unique',
    'gaps:coding:coding_0009':'stable_unique',
    'diverse:search:numeric_versions':'numeric_versions',
    'diverse:coding:version_compare':'numeric_versions',
}


def dump(p,value):
    write(p,json.dumps(value,ensure_ascii=False,indent=2)+'\n')


def input_hash(path):
    h=hashlib.sha256()
    for p in sorted(path.rglob('*')):
        if p.is_file():h.update(p.relative_to(path).as_posix().encode()+b'\0'+p.read_bytes())
    return h.hexdigest()


def metadata():
    if (META/'manifest.json').exists():return json.loads((META/'manifest.json').read_text(encoding='utf-8'))
    rows=[];rng=random.Random(SEED)
    for source in ('diverse','gaps','tricks'):
        base=ROOT/'benchmarks'/(source+'-v1')
        original=json.loads((base/'manifest.json').read_text(encoding='utf-8'))['tasks']
        held={r['id'] for r in original if r.get('split')=='holdout'}
        if source=='gaps':
            for kind in KINDS:
                for solvable in (True,False):
                    held.add(rng.choice([r for r in original if r['type']==kind and r['solvable']==solvable])['id'])
        if source=='tricks':
            for kind in KINDS:
                pool=[r for r in original if r['type']==kind]
                if kind=='math':
                    held.add(rng.choice([r for r in pool if not r['solvable']])['id'])
                    held.add(rng.choice([r for r in pool if r['solvable']])['id'])
                else:held.update(r['id'] for r in rng.sample(pool,2))
        for r in original:
            family=source+':'+r['type']+':'+r.get('family',r['id'])
            rows.append(dict(id=f'q{len(rows)+1:04}',source=source,source_id=r['id'],type=r['type'],
                family=family,group=ALIASES.get(family,family),solvable=r['solvable'],
                split='holdout' if r['id'] in held else 'train',
                input_sha256=input_hash(base/'input'/r['id'])))
    held_groups={r['group'] for r in rows if r['split']=='holdout'}
    for r in rows:
        if r['group'] in held_groups:r['split']='holdout'
    result=dict(seed=SEED,sources=['diverse-v1','gaps-v1','tricks-v1'],tasks=rows,
        by_split=dict(Counter(r['split'] for r in rows)),
        note='Known exact algorithm overlaps grouped; source-family separation is not proof of full semantic independence.')
    assert len(rows)==132
    assert not ({r['group'] for r in rows if r['split']=='train'}&held_groups)
    dump(META/'manifest.json',result)
    return result


def cached_labels(meta):
    published=ROOT/'docs/results/quality-minilm-v1/cached-labels.json'
    if published.exists():
        result=json.loads(published.read_text(encoding='utf-8'))
        assert len(result)==108 and all(r['cost']>0 for r in result)
        assert {r['id'] for r in result}<={r['id'] for r in meta['tasks']}
        dump(WORK/'cached-labels.json',result)
        return result
    result=[]
    reports={
        'diverse':ROOT/'benchmark-runs/predictors-v1/train-dev/graded.json',
        'gaps':ROOT/'docs/results/2026-11-12/gaps-v1-graded.json',
        'tricks':ROOT/'docs/results/2026-11-12/tricks-v1-graded.json',
    }
    for r in meta['tasks']:
        path=reports[r['source']];report=json.loads(path.read_text(encoding='utf-8'))
        assert report['stop']=='all tasks handled'
        row=next((v for v in report['rows'] if v['id']==r['source_id']),None)
        if row is None:continue
        assert row['cost']>0
        assert r['type']!='coding' or not row['correct'] or row['answer']=='DONE'
        result.append(dict(id=r['id'],correct=int(row['correct']),cost=row['cost'],
            provenance=str(path.relative_to(ROOT)),source_agent_commit='945ecb7'))
    dump(WORK/'cached-labels.json',result)
    dump(published,result)
    return result


def collect_suite(meta,labels):
    out=WORK/'collection-suite'
    if out.exists():return
    known={r['id'] for r in labels};rows=[]
    for r in meta['tasks']:
        if r['id'] in known:continue
        base=ROOT/'benchmarks'/(r['source']+'-v1');old=base/'input'/r['source_id'];ref=base/'references'/r['source_id']
        task=json.loads((old/'task.json').read_text(encoding='utf-8'));task['task_id']=r['id']
        src=old/'workspace' if (old/'workspace').exists() else old
        for p in src.rglob('*'):
            if p.is_file() and p.name!='task.json':
                name=p.relative_to(src)
                write(out/'input'/r['id']/'workspace'/name,p.read_bytes())
                write(out/'references'/r['id']/'workspace'/name,p.read_bytes())
        answer=json.loads((ref/'answer.json').read_text(encoding='utf-8'))['expected']
        write(out/'input'/r['id']/'task.json',json.dumps(task,ensure_ascii=False,indent=2)+'\n')
        dump(out/'references'/r['id']/'task.json',dict(task,expected=answer))
        if (ref/'test_private.py').exists():write(out/'references'/r['id']/'test_private.py',(ref/'test_private.py').read_bytes())
        rows.append(dict(r,reward=task['reward'],check=task['check'],expected=answer))
    dump(out/'manifest.json',dict(tasks=rows,input_sha256=input_hash(out/'input')))


def holdout(meta):
    out=ROOT/'benchmarks/quality-holdout-200'
    if out.exists():raise ValueError('Use a fresh holdout output directory')
    modules=sources();mods=dict(diverse=modules[0],gaps=modules[1],tricks=modules[2])
    allowed={r['family'] for r in meta['tasks'] if r['split']=='holdout'};bank=[]
    for source,m in mods.items():
        for kind in KINDS:
            for i,t in enumerate(cases(m,kind,SEED)):
                family=source+':'+kind+':'+t['family']
                if family in allowed:bank.append((m,source,kind,i,family,t['solvable']))
    rng=random.Random(SEED+1);rewards=random.Random(SEED+991);seen=set();rows=[]
    for kind in KINDS:
        for solvable,count in ((True,40),(False,10)):
            pool=[t for t in bank if t[2]==kind and t[5]==solvable];rng.shuffle(pool)
            assert pool,(kind,solvable)
            made=attempt=0
            while made<count:
                assert attempt<2000,'Insufficient unique instances'
                m,source,_,index,family,_=pool[attempt%len(pool)];attempt+=1
                seed=rng.getrandbits(32);c=adapt(payload(m,kind,index,seed),kind,seed)
                h=hashlib.sha256(c['prompt'].encode())
                for n,v in sorted(c['files'].items()):h.update(n.encode()+b'\0'+(v if isinstance(v,bytes) else v.encode()))
                if h.hexdigest() in seen:continue
                seen.add(h.hexdigest());made+=1;task_id=f'v{len(rows)+1:04}';reward=rewards.randint(1,10)
                task=dict(task_id=task_id,task_type=kind,instruction=c['prompt'],reward=reward,check=c['check'])
                (out/'input'/task_id/'workspace').mkdir(parents=True,exist_ok=True)
                dump(out/'input'/task_id/'task.json',task)
                for n,v in c['files'].items():
                    write(out/'input'/task_id/'workspace'/n,v);write(out/'references'/task_id/'workspace'/n,v)
                dump(out/'references'/task_id/'task.json',dict(task,expected=c['expected']))
                if c['private']:write(out/'references'/task_id/'test_private.py',c['private'])
                if c['reference']:write(out/'references'/task_id/'reference_module.py',c['reference'])
                rows.append(dict(id=task_id,type=kind,source=source,family=family,group=ALIASES.get(family,family),
                    solvable=solvable,reward=reward,check=c['check'],expected=c['expected'],seed=seed,
                    reference_target=c.get('reference_target'),content_sha256=h.hexdigest()))
    train_groups={r['group'] for r in meta['tasks'] if r['split']=='train'}
    assert not (train_groups&{r['group'] for r in rows})
    dump(out/'manifest.json',dict(seed=SEED+1,reward_seed=SEED+991,input_sha256=input_hash(out/'input'),tasks=rows))
    write(out/'.gitattributes','* -text -whitespace\n*.py text eol=lf\n*.md text eol=lf\n')
    print('Frozen holdout:',len(rows),'tasks',len({r['group'] for r in rows}),'groups',flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--holdout',action='store_true');args=p.parse_args()
    meta=metadata()
    if args.holdout:holdout(meta)
    else:
        labels=cached_labels(meta);collect_suite(meta,labels)
        print(json.dumps(dict(split=meta['by_split'],cached=len(labels),new_labels_needed=132-len(labels))),flush=True)
