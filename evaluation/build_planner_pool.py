"""500 grouped task instances from four existing suites; independent random rewards."""
import argparse
from collections import Counter
import hashlib
import importlib.util
import json
from pathlib import Path
import random
import re
import sys
import tempfile

ROOT=Path(__file__).resolve().parents[1]
TAIL=' Work only inside the current directory. When you are done, write ONLY the final answer to answer.txt in the current directory.'


def module(name,path):
    spec=importlib.util.spec_from_file_location(name,ROOT/path);m=importlib.util.module_from_spec(spec)
    sys.modules[name]=m;spec.loader.exec_module(m);return m


def sources():
    diverse=module('pool_diverse','benchmarks/diverse-v1/build.py')
    gaps=module('pool_gaps','benchmarks/gaps-v1/build.py')
    tricks=module('pool_tricks','benchmarks/tricks-v1/build.py')
    from evaluation import build_suite as suite
    return diverse,gaps,tricks,suite


def cases(source,kind,seed):
    m=source;rng=random.Random(seed)
    if m.__name__=='pool_diverse':
        m.SEED=seed;m.CASES.clear()
        {'math':m.maths,'data_analysis':m.data_tasks,'search':m.searches,'coding':m.coding}[kind]()
        return [dict(family=t['family'],prompt=t['prompt']+m.TAIL,expected=t['expected'],check=t['check'],
            solvable=t['solvable'],files=t['files'],private=t['private'],reference=t['reference']) for t in m.CASES]
    return [dict(family=t.id,prompt=t.instruction,expected=t.expected,check=t.check,solvable=t.solvable,
        files=t.files,private=t.private_tests,reference=t.reference_mylib) for t in
        {'math':m.math_tasks,'data_analysis':m.data_tasks,'search':m.search_tasks,'coding':m.coding_tasks}[kind](rng)]


def write(path,data):
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_bytes(data if isinstance(data,bytes) else data.encode('utf-8'))


def payload(source,kind,index,seed):
    if source.__name__!='evaluation.build_suite':return cases(source,kind,seed)[index]
    t=source.TEMPLATES[index]
    with tempfile.TemporaryDirectory() as tmp:
        ws=Path(tmp);s=t.build(random.Random(seed),ws)
        files={p.relative_to(ws).as_posix():p.read_bytes() for p in ws.rglob('*') if p.is_file()}
    return dict(family=t.name,prompt=s['prompt']+TAIL,expected=s['expected'],check=s['check'],
        solvable=t.solvable,files=files,private=s.get('private'),reference=s.get('reference'))


def adapt(case,kind,nonce):
    c=dict(case);c['files']=dict(c['files']);rng=random.Random(nonce)
    if kind=='math' and c['check']=='exact_int':
        offset=rng.randint(1,99999)
        extra=f'For this instance, let q denote the integer quantity requested above. Report q + {offset} instead of q.'
        before,marker,after=c['prompt'].partition('When you are done, write ONLY')
        c['prompt']=before.rstrip()+' '+extra+(' '+marker+after if marker else '')
        if c['solvable']:c['expected']=str(int(c['expected'])+offset)
        c['transform']='integer target offset'
    elif kind=='coding':
        original=next(n for n in ('solution.py','mylib.py') if n in c['files'])
        old=Path(original).stem;new=f'lib_{nonce:08x}';pattern=r'\b'+old+r'\b'
        def transform(data):
            if data is None:return None
            text=data.decode('utf-8') if isinstance(data,bytes) else data
            return re.sub(pattern,new,text)
        c['prompt']=transform(c['prompt'])
        c['files']={new+'.py' if n==original else n:transform(v) if n.endswith('.py') else v for n,v in c['files'].items()}
        c['private']=transform(c['private']);c['reference']=transform(c['reference'])
        c['reference_target']=new+'.py';c['transform']='module rename (same algorithm family)'
    elif kind=='search':
        for i in range(rng.randint(1,5)):
            c['files'][f'kb/archive_{nonce:08x}_{i}.md']=f'Inventory archive {nonce}-{i}: batch Z{rng.randrange(1000000)} contains {rng.randrange(1,99)} crates.\n'
        c['transform']='seeded facts and unrelated inventory documents'
    elif kind=='data_analysis':
        names=[n for n in c['files'] if n.endswith(('.csv','.tsv','.jsonl'))]
        if names:
            old=names[0];new=Path(old).with_name(f'table_{nonce:08x}'+Path(old).suffix).as_posix()
            c['files'][new]=c['files'].pop(old)
            c['prompt']=c['prompt'].replace(old,new)
            for name,value in list(c['files'].items()):
                if name.endswith(('.md','.txt')):
                    text=value.decode('utf-8') if isinstance(value,bytes) else value
                    c['files'][name]=text.replace(old,new)
        c['transform']='seeded table data and file rename'
    else:c['transform']='original parameterized instance'
    return c


def build(output,seed=20261112):
    if output.exists():raise ValueError('Use a new output directory')
    mods=sources();bank=[]
    kinds=('math','data_analysis','search','coding')
    for mi,m in enumerate(mods):
        source=('diverse','gaps','tricks','suite')[mi]
        if mi==3:
            for i,t in enumerate(m.TEMPLATES):bank.append((m,source,t.kind,i,t.name,t.solvable,'train'))
        else:
            for kind in kinds:
                for i,t in enumerate(cases(m,kind,seed)):
                    bank.append((m,source,kind,i,t['family'],t['solvable'],'eval' if mi in (1,2) else 'train'))
    rng=random.Random(seed);rewards=random.Random(seed+991);rows=[];signatures=set();ordinal=0
    for split,per_type in [('train',75),('eval',50)]:
        for kind in kinds:
            for solvable,count in [(True,per_type*4//5),(False,per_type//5)]:
                pool=[t for t in bank if t[2]==kind and t[5]==solvable and t[6]==split]
                if not pool:raise ValueError(f'No families for {split}/{kind}/{solvable}')
                rng.shuffle(pool);made=attempt=0
                while made<count:
                    if attempt>count*20:raise ValueError('Too few unique parameterizations')
                    template=pool[attempt%len(pool)];attempt+=1
                    m,source,_,index,family,_,_=template
                    instance_seed=rng.getrandbits(32)
                    c=adapt(payload(m,kind,index,instance_seed),kind,instance_seed)
                    h=hashlib.sha256(c['prompt'].encode())
                    for n,v in sorted(c['files'].items()):h.update(n.encode()+b'\0'+(v if isinstance(v,bytes) else v.encode()))
                    if h.hexdigest() in signatures:continue
                    signatures.add(h.hexdigest());ordinal+=1;made+=1
                    task_id=f'p{ordinal:04}';reward=rewards.randint(1,10)
                    task=dict(task_id=task_id,task_type=kind,instruction=c['prompt'],reward=reward,check=c['check'])
                    base=output/split;work=base/'input'/task_id/'workspace';work.mkdir(parents=True)
                    write(base/'input'/task_id/'task.json',json.dumps(task,ensure_ascii=False,indent=2)+'\n')
                    for n,v in c['files'].items():
                        write(work/n,v);write(base/'references'/task_id/'workspace'/n,v)
                    write(base/'references'/task_id/'task.json',json.dumps(dict(task,expected=c['expected']),ensure_ascii=False,indent=2)+'\n')
                    if c['private']:write(base/'references'/task_id/'test_private.py',c['private'])
                    if c['reference']:write(base/'references'/task_id/'reference_module.py',c['reference'])
                    rows.append(dict(id=task_id,type=kind,source=source,family=source+':'+kind+':'+family,split=split,
                        solvable=solvable,reward=reward,expected=c['expected'],check=c['check'],seed=instance_seed,
                        transformation=c['transform'],reference_target=c.get('reference_target'),content_sha256=h.hexdigest()))
    assert len(rows)==500 and len(signatures)==500
    assert not ({r['family'] for r in rows if r['split']=='train'} & {r['family'] for r in rows if r['split']=='eval'})
    for split in ('train','eval'):
        h=hashlib.sha256()
        for p in sorted((output/split/'input').rglob('*')):
            if p.is_file():h.update(p.relative_to(output/split/'input').as_posix().encode()+b'\0'+p.read_bytes())
        manifest=dict(seed=seed,reward_seed=seed+991,reward_range=[1,10],split=split,input_sha256=h.hexdigest(),
            tasks=[r for r in rows if r['split']==split])
        write(output/split/'manifest.json',json.dumps(manifest,ensure_ascii=False,indent=2)+'\n')
    summary=dict(count=500,seed=seed,families=len({r['family'] for r in rows}),by_type=dict(Counter(r['type'] for r in rows)),
        by_split=dict(Counter(r['split'] for r in rows)),unavailable=sum(not r['solvable'] for r in rows),unique_inputs=len(signatures))
    write(output/'summary.json',json.dumps(summary,indent=2)+'\n');print(json.dumps(summary),flush=True)
    write(output/'.gitattributes','# Fixtures intentionally include CRLF, trailing spaces and blank final lines.\n* -text -whitespace\n*.py text eol=lf\n*.md text eol=lf\n')


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--out',type=Path,default=ROOT/'benchmarks/planner-500');p.add_argument('--seed',type=int,default=20261112)
    a=p.parse_args();build(a.out,a.seed)
