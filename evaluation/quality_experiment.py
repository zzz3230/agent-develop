"""Collect missing holdout labels, evaluate frozen heads, and compare once at 50k."""
import argparse
from datetime import datetime,timezone
import hashlib
import json
import random
import shutil

from evaluation.quality_dataset import ROOT,META,WORK,dump,input_hash
from evaluation.run_image import run
from evaluation.compare_pool_predictors import summarize

MODES=('quality_minilm_keywords','quality_minilm_structural')
IMAGE='agent-develop:quality-minilm'
REPORT=ROOT/'docs/results/quality-minilm-v1'


def freeze():
    models={m:hashlib.sha256((ROOT/'predictors'/(m+'.json')).read_bytes()).hexdigest() for m in MODES}
    path=WORK/'frozen-models.json'
    if path.exists():
        saved=json.loads(path.read_text(encoding='utf-8'));assert saved['models']==models,'Frozen models changed'
    else:dump(path,dict(models=models,utc=datetime.now(timezone.utc).isoformat(),
        split_sha256=hashlib.sha256((META/'manifest.json').read_bytes()).hexdigest()))
    return models


def collect():
    freeze();suite=WORK/'collection-suite';target=WORK/'collection-run'
    if not target.exists() and (REPORT/'new-labels.json').exists():
        print('Reusing published 24 completed validation measurements; no API calls.',flush=True)
        return
    if not (target/'graded.json').exists():
        run('agent-develop:predictor-policies',suite/'input',target,
            env={'QUEUE':'0','RETRY':'0','BUDGET':'1000000','ENFORCE_BUDGET':'0'},
            references=suite,commit='f8e23acab8083a1ae7172c05b6033b83c22ee761',quiet=True)
    result=json.loads((target/'graded.json').read_text(encoding='utf-8'))
    assert result['stop']=='all tasks handled','Incomplete held-out collection'
    assert len(result['rows'])==24 and all(r.get('cost',0)>0 for r in result['rows'])
    dump(REPORT/'new-labels.json',[dict(id=r['id'],correct=int(r['correct']),cost=r['cost'],
        provenance='benchmark-runs/quality-minilm-v1/collection-run',source_agent_commit='f8e23ac') for r in result['rows']])
    dump(REPORT/'collection.json',dict(total=result['total'],spent=result['spent'],
        source_agent_commit='f8e23ac',model_hashes=freeze()))
    print('COLLECTED '+json.dumps(dict(spent=result['spent'],correct=result['total']['correct'])),flush=True)


def validate_heads():
    import numpy as np
    from sklearn.metrics import brier_score_loss,mean_absolute_error,log_loss
    from runtime.predictor import Predictor
    from runtime.tasks import load_task
    frozen=freeze();meta=json.loads((META/'manifest.json').read_text(encoding='utf-8'))
    labels={r['id']:r for name in (WORK/'cached-labels.json',REPORT/'new-labels.json')
            for r in json.loads(name.read_text(encoding='utf-8'))}
    held=[r for r in meta['tasks'] if r['split']=='holdout'];tasks=[]
    for r in held:
        path=ROOT/'benchmarks'/(r['source']+'-v1')/'input'/r['source_id']
        assert input_hash(path)==r['input_sha256']
        t=load_task(path)
        from dataclasses import replace
        tasks.append(replace(t,id=r['id']))
    y=np.array([labels[r['id']]['correct'] for r in held]);cost=np.array([labels[r['id']]['cost'] for r in held])
    metrics={}
    for mode in MODES:
        model=Predictor(tasks,mode,ROOT/'predictors')
        p,c=zip(*(model.predictions[r['id']] for r in held))
        metrics[mode]=dict(brier=float(brier_score_loss(y,p)),log_loss=float(log_loss(y,p)),
            cost_mae=float(mean_absolute_error(cost,c)),probability_min=float(min(p)),
            probability_max=float(max(p)),probability_std=float(np.std(p)),
            predicted_cost_min=float(min(c)),predicted_cost_max=float(max(c)))
    training=json.loads((REPORT/'training-data.json').read_text(encoding='utf-8'))
    baseline_p=sum(r['correct'] for r in training)/len(training);baseline_c=sum(r['cost'] for r in training)/len(training)
    metrics['constant_training_mean']=dict(brier=float(brier_score_loss(y,np.full(len(y),baseline_p))),
        log_loss=float(log_loss(y,np.full(len(y),baseline_p))),cost_mae=float(mean_absolute_error(cost,np.full(len(y),baseline_c))))
    assert freeze()==frozen
    dump(REPORT/'holdout-metrics.json',dict(tasks=len(held),correct=int(y.sum()),metrics=metrics,model_hashes=frozen,
        note='Only prediction evaluation; no fitting, calibration or hyperparameter selection on these labels.'))
    print('HOLDOUT '+json.dumps(metrics),flush=True)


def compare():
    model_hashes=freeze();suite=ROOT/'benchmarks/quality-holdout-200';order_dir=WORK/'order-101'
    manifest=json.loads((suite/'manifest.json').read_text(encoding='utf-8'))
    assert input_hash(suite/'input')==manifest['input_sha256']
    if not order_dir.exists():
        folders=sorted((suite/'input').iterdir());random.Random(101).shuffle(folders)
        for i,folder in enumerate(folders):shutil.copytree(folder,order_dir/f'{i:04}_{folder.name}')
    order=list(MODES);random.Random(101).shuffle(order)
    protocol=dict(tasks=200,budget=50000,repeats=1,score_alpha=1,policy='greedy',mode_order=order,
        image=IMAGE,original_input_sha256=manifest['input_sha256'],input_sha256=input_hash(order_dir),
        model_hashes=model_hashes,training_rows=88,heldout_source_tasks=44,
        description='Quality-only training; semantic/source groups in workload do not occur in training. Known development benchmarks, not blind external validation.')
    pp=WORK/'comparison/protocol.json'
    if pp.exists():assert json.loads(pp.read_text(encoding='utf-8'))==protocol
    else:dump(pp,protocol)
    rows=[]
    for mode in order:
        target=WORK/'comparison'/mode
        if not (target/'graded.json').exists():
            print('START '+mode,flush=True)
            run(IMAGE,order_dir,target,
                env={'PREDICTOR':mode,'QUEUE':'1','QUEUE_POLICY':'greedy','SCORE_ALPHA':'1','RETRY':'0',
                     'BUDGET':'50000','ENFORCE_BUDGET':'1'},hard_budget=50000,references=suite,quiet=True,
                commit=json.loads((WORK/'candidate.json').read_text(encoding='utf-8'))['commit'])
        row=summarize(target)
        assert row['exit_code'] in (0,137),'Infrastructure/agent error'
        assert row['spent']>=50000 or row['completed']==200,'Incomplete trial'
        rows.append(row);dump(WORK/'comparison/results.json',rows)
        print('RESULT '+json.dumps(row),flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('stage',choices=['collect','validate','compare']);a=p.parse_args()
    {'collect':collect,'validate':validate_heads,'compare':compare}[a.stage]()
