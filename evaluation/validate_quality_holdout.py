"""Check split isolation, immutable input bytes and all coding oracles; no LLM."""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile


def validate(root,split,coding=False):
    m=json.loads((root/'manifest.json').read_text(encoding='utf-8'))
    partition=json.loads(split.read_text(encoding='utf-8'))
    train={r['group'] for r in partition['tasks'] if r['split']=='train'}
    held={r['group'] for r in partition['tasks'] if r['split']=='holdout'}
    rows=m['tasks'];assert len(rows)==200
    assert Counter(r['type'] for r in rows)==dict.fromkeys(('math','data_analysis','search','coding'),50)
    assert sum(not r['solvable'] for r in rows)==40
    assert {r['group'] for r in rows}<=held and not {r['group'] for r in rows}&train
    h=hashlib.sha256()
    for p in sorted((root/'input').rglob('*')):
        if p.is_file():h.update(p.relative_to(root/'input').as_posix().encode()+b'\0'+p.read_bytes())
    assert h.hexdigest()==m['input_sha256']
    assert len({r['content_sha256'] for r in rows})==200
    passed=0
    for r in rows:
        task=root/'input'/r['id'];ref=root/'references'/r['id']
        raw=json.loads((task/'task.json').read_text(encoding='utf-8'))
        expected=json.loads((ref/'task.json').read_text(encoding='utf-8'))
        assert expected==dict(raw,expected=r['expected']) and raw['reward']==r['reward']
        assert not list(task.rglob('test_private*')) and not (task/'answer.txt').exists()
        if 'For this instance, let q denote' in raw['instruction']:
            visible=re.sub(r'\s*When you are done, write ONLY.*$','',raw['instruction'],flags=re.S)
            assert 'For this instance, let q denote' in visible
        if not coding or r['type']!='coding' or not r['solvable']:continue
        with tempfile.TemporaryDirectory() as tmp:
            work=Path(tmp);shutil.copytree(ref/'workspace',work,dirs_exist_ok=True)
            shutil.copy2(ref/'reference_module.py',work/r['reference_target'])
            if (ref/'test_private.py').exists():shutil.copy2(ref/'test_private.py',work/'test_private.py')
            p=subprocess.run([sys.executable,'-I','-B','-m','unittest','discover','-q'],cwd=work,
                capture_output=True,text=True,encoding='utf-8',errors='replace',timeout=30)
            assert p.returncode==0,r['id']+' '+p.stderr[-2500:]
            passed+=1
    print(json.dumps(dict(tasks=200,groups=len({r['group'] for r in rows}),coding_oracles_passed=passed)),flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('root',type=Path);p.add_argument('split',type=Path)
    p.add_argument('--coding',action='store_true');a=p.parse_args();validate(a.root,a.split,a.coding)
