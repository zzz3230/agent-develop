"""Train-only OOF replay for reward exponents and expected-value knapsack."""
import argparse
import json
import math
from pathlib import Path
import random
import statistics
import time
from evaluation.predictor_experiment import ROOT,OUT,dump
from runtime.planning import knapsack


def episode(records,n,seed):
    rng=random.Random(seed)
    # Rewards resampled independently of task family/source, as in the contest rules.
    return [dict(records[i],reward=rng.randint(1,10)) for i in rng.sample(range(len(records)),n)]


def replay(tasks,budget,alpha=1,policy='greedy'):
    remaining=list(range(len(tasks)));spent=points=0;completed=[]
    scores=[r['reward']**alpha*r['p']/r['predicted_cost'] for r in tasks]
    remaining.sort(key=lambda i:-scores[i])
    while remaining and spent<budget:
        left=budget-spent
        if policy=='knapsack':
            # DP ties follow original directory order, matching the live queue.
            original=sorted(remaining)
            chosen=knapsack([(tasks[i]['reward']*tasks[i]['p'],tasks[i]['predicted_cost']) for i in original],left)
            selected={original[i] for i in chosen}
            candidates=[i for i in remaining if i in selected]
        else:candidates=[]
        if not candidates:
            candidates=[i for i in remaining if tasks[i]['predicted_cost']<=left] or remaining
        i=candidates[0];remaining.remove(i);spent+=tasks[i]['actual_cost']
        # Whole-attempt censoring: no credit for a task crossing the replay budget.
        if spent<=budget:
            points+=tasks[i]['reward']*tasks[i]['correct'];completed.append(i)
    return dict(points=points,whole_attempt_cost=spent,completed=completed)


def tune(records,n,budget):
    episodes=[episode(records,n,1000+s) for s in range(100)]
    results={}
    def evaluate(alpha):
        if alpha not in results:
            scores=[replay(e,budget,alpha)['points'] for e in episodes]
            results[alpha]=dict(mean=statistics.mean(scores),minimum=min(scores),maximum=max(scores))
    for a in [i/4 for i in range(17)]:evaluate(a)
    best=max(results,key=lambda a:(results[a]['mean'],-abs(a-1)))
    for k in range(-5,6):evaluate(round(max(0,min(4,best+k*.05)),2))
    best=max(results,key=lambda a:(results[a]['mean'],-abs(a-1)))
    validation=[]
    for seed in range(10000,10010 if n==34 else 10005):
        e=episode(records,n,seed)
        validation.append(dict(seed=seed,greedy=replay(e,budget,1)['points'],
            tuned=replay(e,budget,best)['points'],knapsack=replay(e,budget,1,'knapsack')['points']))
    return dict(tasks=n,budget=budget,selected_alpha=best,grid={str(k):v for k,v in sorted(results.items())},
        validation_replays=validation,validation_means={k:statistics.mean(v[k] for v in validation) for k in ('greedy','tuned','knapsack')})


def main(mode,scarce=False):
    import numpy as np
    from sklearn.linear_model import LogisticRegression,Ridge
    from sklearn.model_selection import GroupKFold
    from sklearn.preprocessing import StandardScaler
    from evaluation.train_predictors import dataset
    from evaluation.predictor_data import matrix
    started=time.monotonic();rows=dataset();x=matrix(rows,mode)
    model=json.loads((ROOT/'predictors'/f'{mode}.json').read_text(encoding='utf-8'))
    y=np.array([r['correct'] for r in rows]);cost=np.array([r['cost'] for r in rows]);groups=[r['group'] for r in rows]
    p=np.zeros(len(y));c=np.zeros(len(y))
    for a,b in GroupKFold(n_splits=5).split(x,y,groups):
        scaler=StandardScaler().fit(x[a]);xa=scaler.transform(x[a]);xb=scaler.transform(x[b])
        cls=LogisticRegression(C=model['validation']['C'],max_iter=2000,random_state=71).fit(xa,y[a])
        reg=Ridge(alpha=model['validation']['alpha']).fit(xa,cost[a])
        p[b]=np.clip(cls.predict_proba(xb)[:,1],.02,.98);c[b]=np.clip(reg.predict(xb),50,20000)
    records=[dict(id=r['task'].id,group=r['group'],p=float(p[i]),predicted_cost=float(c[i]),
        actual_cost=r['cost'],correct=r['correct']) for i,r in enumerate(rows)]
    dump(OUT/'planning-oof.json',dict(mode=mode,training_sha256=model['training_sha256'],records=records))
    report=dict(mode=mode,training_sha256=model['training_sha256'],scenarios=[])
    for n,budget in ([(34,6000)] if scarce else [(34,12000),(100,100000)]):
        scenario=tune(records,n,budget);report['scenarios'].append(scenario)
        print('TUNED '+json.dumps({k:v for k,v in scenario.items() if k not in ('grid','validation_replays')}),flush=True)
    report['seconds']=time.monotonic()-started
    report['limitations']=['Repeated resampling of the same 140 attempts is not new independent data.',
        'Validation seeds change rewards/order, not task families; real runs remain necessary.',
        'Replay censors the entire crossing attempt; proxy cuts may occur mid-task.',
        'Predictor hyperparameters were already selected on these training groups.']
    dump(OUT/('planning-tuning-6000.json' if scarce else 'planning-tuning.json'),report)


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--mode',required=True);parser.add_argument('--scarce',action='store_true');args=parser.parse_args();main(args.mode,args.scarce)
