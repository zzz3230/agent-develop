"""Validate frozen pool metadata and all coding reference implementations; no LLM."""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile


def validate(root,coding=False):
    rows=[]
    for split in ('train','eval'):
        m=json.loads((root/split/'manifest.json').read_text(encoding='utf-8'));rows+=m['tasks'];h=hashlib.sha256()
        for p in sorted((root/split/'input').rglob('*')):
            if p.is_file():h.update(p.relative_to(root/split/'input').as_posix().encode()+b'\0'+p.read_bytes())
        assert h.hexdigest()==m['input_sha256'],'Input hash mismatch'
        for r in m['tasks']:
            p=root/split/'input'/r['id'];raw=json.loads((p/'task.json').read_text(encoding='utf-8'))
            assert set(raw)=={'task_id','task_type','instruction','reward','check'}
            assert raw['reward']==r['reward'] and 1<=r['reward']<=10
            reference=json.loads((root/split/'references'/r['id']/'task.json').read_text(encoding='utf-8'))
            assert reference==dict(raw,expected=r['expected']),r['id']
            assert not list(p.rglob('test_private*')) and not (p/'answer.txt').exists()
            if r['solvable'] and r['check']=='exact_int':int(r['expected'])
    assert len(rows)==500 and len({r['content_sha256'] for r in rows})==500
    assert Counter(r['type'] for r in rows)==dict.fromkeys(['math','data_analysis','search','coding'],125)
    assert sum(not r['solvable'] for r in rows)==100
    assert not ({r['family'] for r in rows if r['split']=='train'} & {r['family'] for r in rows if r['split']=='eval'})
    passed=0
    if coding:
        for r in rows:
            if r['type']!='coding' or not r['solvable']:continue
            ref=root/r['split']/'references'/r['id']
            assert (ref/'reference_module.py').exists(),r['id']
            with tempfile.TemporaryDirectory() as tmp:
                work=Path(tmp);shutil.copytree(ref/'workspace',work,dirs_exist_ok=True)
                shutil.copy2(ref/'reference_module.py',work/r['reference_target'])
                if (ref/'test_private.py').exists():shutil.copy2(ref/'test_private.py',work/'test_private.py')
                p=subprocess.run([sys.executable,'-I','-B','-m','unittest','discover','-q'],cwd=work,
                    capture_output=True,text=True,encoding='utf-8',errors='replace',timeout=30)
                if p.returncode:raise AssertionError(r['id']+' '+r['family']+'\n'+p.stderr[-3000:])
                passed+=1
    print(json.dumps(dict(tasks=len(rows),coding_oracles_passed=passed,families=len({r['family'] for r in rows}),
        rewards=dict(Counter(r['reward'] for r in rows))),sort_keys=True),flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('root',type=Path);p.add_argument('--coding',action='store_true');a=p.parse_args();validate(a.root,a.coding)
