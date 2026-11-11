"""Train frozen regularized predictors, validate by task family; no held-out inputs loaded."""
import hashlib
import json
from pathlib import Path
import time

import numpy as np
from sklearn.linear_model import LogisticRegression, Ridge
from sklearn.preprocessing import StandardScaler
from sklearn.model_selection import GroupKFold
from sklearn.metrics import brier_score_loss, log_loss, mean_absolute_error

from runtime.tasks import load_task
from runtime.predictor import features, Encoder
from evaluation.predictor_experiment import ROOT,OUT,TRAIN_SUITE,dump


def dataset():
    rows=[]
    for label,manifest,inputs in [
        ('train-old',TRAIN_SUITE/'manifest.json',TRAIN_SUITE/'input'),
        ('train-dev',ROOT/'benchmarks/diverse-v1/manifest.json',ROOT/'benchmarks/diverse-v1/input')]:
        metadata={r['id']:r for r in json.loads(manifest.read_text(encoding='utf-8'))['tasks']}
        report=json.loads((OUT/label/'graded.json').read_text(encoding='utf-8'))
        if report.get('stop')!='all tasks handled': raise ValueError('Incomplete collection: '+label)
        events=[json.loads(s) for s in (OUT/label/'harness/trajectory.jsonl').read_text(encoding='utf-8').splitlines()]
        finished={e['task'] for e in events if e['event']=='outcome'}
        for r in report['rows']:
            if r['id'] not in finished or r.get('cost',0)<=0: continue
            m=metadata[r['id']]
            if label=='train-dev' and m['split']!='dev': raise ValueError('Holdout contamination')
            task=load_task(inputs/r['id'])
            group=label+':'+r['type']+':'+str(m['family'])+(':'+str(m.get('solvable')) if label=='train-old' else '')
            rows.append(dict(task=task,group=group,correct=int(r['correct']),cost=r['cost']))
    return rows


def train(extensions=False,combined=False,full_keywords=False):
    if combined or full_keywords: extensions=True
    started=time.monotonic();rows=dataset()
    if len(rows)<100: raise ValueError('Collection incomplete; need at least 100 charged completed tasks')
    numeric=np.asarray([features(r['task'],keywords=not extensions or full_keywords) for r in rows])
    from evaluation.predictor_data import embedded
    embeddings=embedded(rows,extensions)
    y=np.array([r['correct'] for r in rows]);cost=np.array([r['cost'] for r in rows]);groups=[r['group'] for r in rows]
    provenance=[dict(id=r['task'].id,group=r['group'],correct=r['correct'],cost=r['cost']) for r in rows]
    digest=hashlib.sha256(json.dumps(provenance,sort_keys=True).encode()).hexdigest()
    dump(OUT/'training_rows.json',provenance)
    report=dict(training_rows=len(rows),successes=int(y.sum()),groups=len(set(groups)),training_sha256=digest,models={})
    baseline_p=np.zeros(len(y));baseline_c=np.zeros(len(y))
    for a,b in GroupKFold(n_splits=5).split(numeric,y,groups):
        for j in b:
            kind=rows[j]['task'].type
            relevant=[i for i in a if rows[i]['task'].type==kind]
            baseline_p[j]=(sum(y[i] for i in relevant)+1)/(len(relevant)+2)
            baseline_c[j]=np.mean(cost[relevant]) if relevant else np.mean(cost[a])
    report['offline_type_only_reference']=dict(brier=float(brier_score_loss(y,baseline_p)),
        log_loss=float(log_loss(y,baseline_p)),cost_mae=float(mean_absolute_error(cost,baseline_c)))
    variants=[('structural',numeric),('strong_embedding',embeddings)] if extensions else [('numeric',numeric),('embedding',np.hstack([numeric,embeddings]))]
    if combined: variants=[('bge_structural',np.hstack([numeric,embeddings]))]
    if full_keywords: variants=[('bge_keywords',np.hstack([numeric,embeddings]))]
    for mode,x in variants:
        cached=[]
        for a,b in GroupKFold(n_splits=5).split(x,y,groups):
            scaler=StandardScaler().fit(x[a]);cached.append((a,b,scaler.transform(x[a]),scaler.transform(x[b])))
        classifiers=[];regressors=[]
        for strength in [.0001,.001,.01,.1,1]:
            pred=np.zeros(len(y))
            for a,b,xa,xb in cached:
                cls=LogisticRegression(C=strength,max_iter=2000,random_state=71).fit(xa,y[a])
                pred[b]=cls.predict_proba(xb)[:,1]
            classifiers.append((float(brier_score_loss(y,pred)),strength,pred))
        for strength in [10,100,1000,10000]:
            pred=np.zeros(len(y))
            for a,b,xa,xb in cached:
                reg=Ridge(alpha=strength).fit(xa,cost[a]);pred[b]=np.clip(reg.predict(xb),50,20000)
            regressors.append((float(np.mean((cost-pred)**2)),strength,pred))
        _,best_c,probabilities=min(classifiers,key=lambda row:row[0])
        _,best_alpha,predicted=min(regressors,key=lambda row:row[0])
        scaler=StandardScaler().fit(x);xx=scaler.transform(x)
        cls=LogisticRegression(C=best_c,max_iter=2000,random_state=71).fit(xx,y)
        reg=Ridge(alpha=best_alpha).fit(xx,cost)
        metrics=dict(brier=float(brier_score_loss(y,probabilities)),log_loss=float(log_loss(y,probabilities)),
                     cost_mae=float(mean_absolute_error(cost,predicted)),C=best_c,alpha=best_alpha,
                     selection_brier={str(c):loss for loss,c,_ in classifiers},
                     selection_cost_mse={str(a):loss for loss,a,_ in regressors})
        model=dict(mode=mode,mean=scaler.mean_.tolist(),scale=scaler.scale_.tolist(),
                   success=dict(coef=cls.coef_[0].tolist(),intercept=float(cls.intercept_[0])),
                   cost=dict(coef=reg.coef_.tolist(),intercept=float(reg.intercept_)),
                   cost_transform='identity',log_bias=0,training_sha256=digest,validation=metrics)
        dump(ROOT/'predictors'/(mode+'.json'),model);report['models'][mode]=metrics
    report['seconds']=time.monotonic()-started
    dump(OUT/('training_report_keywords.json' if full_keywords else 'training_report_combined.json' if combined else 'training_report_extensions.json' if extensions else 'training_report.json'),report)
    print(json.dumps(report,indent=2))


if __name__=='__main__':
    import argparse
    parser=argparse.ArgumentParser();parser.add_argument('--extensions',action='store_true')
    parser.add_argument('--bge-structural',action='store_true');parser.add_argument('--bge-keywords',action='store_true');args=parser.parse_args()
    train(args.extensions,args.bge_structural,args.bge_keywords)
