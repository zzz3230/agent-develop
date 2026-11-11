"""Bounded pre-attempt features and frozen linear predictors; no reference access."""
import json
import math
import os
from pathlib import Path
import re
import time

KINDS=('math','data_analysis','search','coding')
WORDS=('round','date','latest','before','after','distinct','duplicate','missing','except',
       'maximum','minimum','path','dependency','cycle','sort','order','integer','decimal',
       'probability','exact','return','revision','effective','timezone','invalid','raise')
SUFFIXES=('.csv','.tsv','.json','.jsonl','.md','.txt','.py')


def features(task,keywords=True):
    text=task.instruction.lower()
    values=[float(task.type==k) for k in KINDS]
    values += [math.log1p(len(text)),math.log1p(len(text.split()))]
    if keywords:
        values += [math.log1p(len(re.findall(r'\b'+w+r'\w*',text))) for w in WORDS]
    counts={s:0 for s in SUFFIXES}; size=files=lines=code_lines=tests=columns=0
    sample_budget=262144
    for path in sorted(task.cwd.rglob('*')):
        if files>=512: break
        if not path.is_file() or path.is_symlink() or '__pycache__' in path.parts: continue
        if path.name in ('task.json','answer.txt','.answer.tmp') or path.name.startswith('test_private'): continue
        files+=1; size+=path.stat().st_size
        suffix=path.suffix.lower()
        if suffix in counts: counts[suffix]+=1
        if suffix in SUFFIXES and sample_budget>0:
            with path.open('rb') as stream: raw=stream.read(min(16384,sample_budget))
            sample_budget-=len(raw); content=raw.decode('utf-8',errors='replace')
            lines+=content.count('\n')
            if suffix=='.py':
                code_lines+=content.count('\n')
                if keywords: tests+=len(re.findall(r'\bassert\w*|def test_',content))
            if suffix in ('.csv','.tsv'):
                first=content.splitlines()[0] if content.splitlines() else ''
                columns=max(columns,first.count('\t' if suffix=='.tsv' else ',')+1)
    values += [math.log1p(v) for v in (files,size,lines,code_lines,*([tests] if keywords else []),columns,*counts.values())]
    return values


class Encoder:
    def __init__(self,directory):
        import onnxruntime as ort
        from tokenizers import Tokenizer
        directory=Path(directory)
        config=directory/'encoding.json'
        self.settings=json.loads(config.read_text(encoding='utf-8')) if config.exists() else {}
        opts=ort.SessionOptions();opts.intra_op_num_threads=2;opts.inter_op_num_threads=1
        self.session=ort.InferenceSession(str(directory/'model.onnx'),sess_options=opts,providers=['CPUExecutionProvider'])
        self.tokenizer=Tokenizer.from_file(str(directory/'tokenizer.json'))
        self.tokenizer.enable_truncation(max_length=self.settings.get('max_length',256))
        self.tokenizer.enable_padding(length=self.settings.get('padding_length',256),pad_id=0,pad_token='[PAD]')

    def encode(self,texts):
        import numpy as np
        results=[]
        for text in texts:
            # At most 8 overlapping chunks, bounded even on pathological instructions.
            words=text.split();chunks=[' '.join(words[i:i+self.settings.get('chunk_words',140)])
                for i in range(0,min(len(words),self.settings.get('max_words',960)),self.settings.get('chunk_step',120))] or ['']
            encoded=self.tokenizer.encode_batch(chunks)
            feed={'input_ids':np.array([e.ids for e in encoded],dtype=np.int64),
                  'attention_mask':np.array([e.attention_mask for e in encoded],dtype=np.int64),
                  'token_type_ids':np.array([e.type_ids for e in encoded],dtype=np.int64)}
            feed={p.name:feed[p.name] for p in self.session.get_inputs()}
            hidden=self.session.run(None,feed)[0]
            mask=feed['attention_mask'][...,None]
            pooled=hidden[:,0] if self.settings.get('pooling')=='cls' else (hidden*mask).sum(axis=1)/np.maximum(mask.sum(axis=1),1)
            pooled/=np.maximum(np.linalg.norm(pooled,axis=1,keepdims=True),1e-9)
            vector=pooled.mean(axis=0);vector/=max(np.linalg.norm(vector),1e-9)
            results.append(vector)
        return np.asarray(results)


class Predictor:
    def __init__(self,tasks,mode,directory,journal=None):
        started=time.monotonic();directory=Path(directory)
        self.model=json.loads((directory/(mode+'.json')).read_text(encoding='utf-8'))
        if mode=='strong_embedding':
            vectors=Encoder(directory/'encoder-strong').encode([t.instruction for t in tasks]).tolist()
        else:
            vectors=[features(t,keywords=mode!='structural') for t in tasks]
        if mode=='embedding':
            embeddings=Encoder(directory/'encoder').encode([t.instruction for t in tasks])
            vectors=[x+e.tolist() for x,e in zip(vectors,embeddings)]
        self.predictions={t.id:self.predict(x) for t,x in zip(tasks,vectors)}
        if journal:
            journal.write('predictor_init',mode=mode,seconds=round(time.monotonic()-started,3),
                          tasks=len(tasks),model_sha256=self.model.get('training_sha256'))
            for t in tasks:
                p,c=self.predictions[t.id];journal.write('prediction',task=t.id,p=p,cost=c)

    def predict(self,features):
        m=self.model
        if len(features)!=len(m['mean']): raise ValueError('Predictor feature schema mismatch')
        x=[(v-a)/s for v,a,s in zip(features,m['mean'],m['scale'])]
        def linear(key): return m[key]['intercept']+sum(a*b for a,b in zip(m[key]['coef'],x))
        p=1/(1+math.exp(-max(-30,min(30,linear('success')))))
        c=linear('cost') if m.get('cost_transform')=='identity' else math.exp(max(0,min(12,linear('cost')+m['log_bias'])))-1
        return max(.02,min(.98,p)),max(50,min(20000,c))
