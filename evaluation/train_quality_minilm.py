"""Fit two MiniLM ablations using only the frozen quality training partition."""
from collections import Counter
import hashlib
import json
import time

import numpy as np
from sklearn.linear_model import LogisticRegression,Ridge
from sklearn.metrics import brier_score_loss,mean_absolute_error,log_loss
from sklearn.model_selection import GroupKFold
from sklearn.preprocessing import StandardScaler

from runtime.tasks import load_task
from runtime.predictor import features
from evaluation.predictor_data import embedded
from evaluation.quality_dataset import ROOT,META,WORK,dump,input_hash


def train():
    started=time.monotonic()
    meta=json.loads((META/'manifest.json').read_text(encoding='utf-8'))
    train_ids={r['id'] for r in meta['tasks'] if r['split']=='train'}
    labels={r['id']:r for r in json.loads((WORK/'cached-labels.json').read_text(encoding='utf-8')) if r['id'] in train_ids}
    rows=[]
    for r in meta['tasks']:
        if r['split']!='train':continue
        path=ROOT/'benchmarks'/(r['source']+'-v1')/'input'/r['source_id']
        assert input_hash(path)==r['input_sha256'],'Source changed after split freeze'
        rows.append(dict(r,task=load_task(path),correct=labels[r['id']]['correct'],cost=labels[r['id']]['cost'],
                         label_provenance=labels[r['id']]['provenance']))
    assert len(rows)==88 and len({r['group'] for r in rows})>=60
    held_groups={r['group'] for r in meta['tasks'] if r['split']=='holdout'}
    assert not held_groups&{r['group'] for r in rows}
    provenance=[{k:v for k,v in r.items() if k!='task'} for r in rows]
    digest=hashlib.sha256(json.dumps(provenance,sort_keys=True).encode()).hexdigest()
    report=dict(training_sha256=digest,training_rows=len(rows),groups=len({r['group'] for r in rows}),
        sources=dict(Counter(r['source'] for r in rows)),successes=sum(r['correct'] for r in rows),models={},
        validation_note='Training-only five-fold family selection metrics, optimistic; holdout labels not used for fitting or selection.')
    vectors=embedded(rows,False);y=np.array([r['correct'] for r in rows]);cost=np.array([r['cost'] for r in rows]);groups=[r['group'] for r in rows]
    for keywords,mode in [(True,'quality_minilm_keywords'),(False,'quality_minilm_structural')]:
        numeric=np.asarray([features(r['task'],keywords=keywords) for r in rows]);x=np.hstack([numeric,vectors])
        folds=[]
        for a,b in GroupKFold(n_splits=5).split(x,y,groups):
            scaler=StandardScaler().fit(x[a]);folds.append((a,b,scaler.transform(x[a]),scaler.transform(x[b])))
        candidates=[]
        for c in (.0001,.001,.01,.1,1):
            pred=np.zeros(len(y))
            for a,b,xa,xb in folds:pred[b]=LogisticRegression(C=c,max_iter=2000,random_state=71).fit(xa,y[a]).predict_proba(xb)[:,1]
            candidates.append((brier_score_loss(y,pred),c,pred))
        _,best_c,prob=min(candidates,key=lambda r:r[0]);cost_candidates=[]
        for alpha in (10,100,1000,10000):
            pred=np.zeros(len(y))
            for a,b,xa,xb in folds:pred[b]=np.clip(Ridge(alpha=alpha).fit(xa,cost[a]).predict(xb),50,20000)
            cost_candidates.append((np.mean((cost-pred)**2),alpha,pred))
        _,best_alpha,predicted=min(cost_candidates,key=lambda r:r[0])
        scaler=StandardScaler().fit(x);xx=scaler.transform(x)
        classifier=LogisticRegression(C=best_c,max_iter=2000,random_state=71).fit(xx,y)
        regressor=Ridge(alpha=best_alpha).fit(xx,cost)
        metrics=dict(brier=float(brier_score_loss(y,prob)),log_loss=float(log_loss(y,prob)),
            cost_mae=float(mean_absolute_error(cost,predicted)),C=best_c,alpha=best_alpha,
            selection_brier={str(c):float(loss) for loss,c,_ in candidates},
            selection_cost_mse={str(a):float(loss) for loss,a,_ in cost_candidates})
        model=dict(mode=mode,mean=scaler.mean_.tolist(),scale=scaler.scale_.tolist(),
            success=dict(coef=classifier.coef_[0].tolist(),intercept=float(classifier.intercept_[0])),
            cost=dict(coef=regressor.coef_.tolist(),intercept=float(regressor.intercept_)),
            cost_transform='identity',log_bias=0,training_sha256=digest,validation=metrics,
            training_sources=report['sources'],feature_keywords=keywords,feature_count=x.shape[1])
        assert x.shape[1]==(429 if keywords else 402)
        dump(ROOT/'predictors'/(mode+'.json'),model);report['models'][mode]=metrics
    report['seconds']=time.monotonic()-started
    dump(ROOT/'docs/results/quality-minilm-v1/training-data.json',provenance)
    dump(ROOT/'docs/results/quality-minilm-v1/training.json',report)
    print(json.dumps(report),flush=True)


if __name__=='__main__':train()
