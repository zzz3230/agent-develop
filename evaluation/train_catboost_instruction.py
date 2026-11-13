"""Fit the four selected instruction-structure features on stored attempts."""
import json

import numpy as np
from sklearn.metrics import brier_score_loss
from sklearn.model_selection import GroupKFold

from evaluation.catboost_cost_ablation import metrics
from evaluation.compare_all_predictors import policy_cohort, replay
from evaluation.quality_dataset import ROOT
from evaluation.train_catboost_extended import classifier, regressor
from evaluation.train_catboost_large import REPORT, load_training_rows
from runtime.predictor import features
from runtime.tasks import load_task


def vector(task):
    return features(task,keywords=False,extended='instruction')


def main():
    selected=json.loads((REPORT/'catboost-feature-subsets.json').read_text(encoding='utf-8'))['selected']
    assert selected=='instruction'
    rows,quality,labels,held_groups=load_training_rows()
    x=np.asarray([vector(r['task']) for r in rows],dtype=np.float32)
    y=np.asarray([r['correct'] for r in rows]);cost=np.asarray([r['cost'] for r in rows])
    groups=[r['group'] for r in rows]
    assert x.shape==(301,22) and not set(groups)&held_groups
    folds=list(GroupKFold(n_splits=5).split(x,y,groups))
    p=np.zeros(len(rows));c=np.zeros(len(rows))
    for train,test in folds:
        p[test]=classifier(x[train],y[train]).predict_proba(x[test])[:,1]
        c[test]=np.maximum(50,regressor('MAE',x[train],cost[train]).predict(x[test]))
    clf=classifier(x,y);reg=regressor('MAE',x,cost)
    clf.save_model(str(ROOT/'predictors/catboost_instruction_success.cbm'))
    reg.save_model(str(ROOT/'predictors/catboost_instruction_cost.cbm'))
    held=[r for r in quality if r['split']=='holdout']
    hx=np.asarray([vector(load_task(ROOT/'benchmarks'/(r['source']+'-v1')/'input'/r['source_id']))
                   for r in held],dtype=np.float32)
    hc=np.asarray([labels[r['id']]['cost'] for r in held])
    hy=np.asarray([labels[r['id']]['correct'] for r in held])
    cohort=policy_cohort();cx=np.asarray([vector(t) for t,_ in cohort],dtype=np.float32)
    cc=np.asarray([r['cost'] for _,r in cohort]);cp=np.maximum(50,reg.predict(cx))
    ordering={t.id:(.5,float(price)) for (t,_),price in zip(cohort,cp)}
    report=dict(rows=len(rows),groups=len(set(groups)),features=22,
                feature_names='18 existing structural + numbers, dates, file references, missing file references',
                group_cv=dict(brier=float(brier_score_loss(y,p)),cost=metrics(cost,c)),
                holdout_diagnostic=dict(brier=float(brier_score_loss(hy,clf.predict_proba(hx)[:,1])),
                                        cost=metrics(hc,np.maximum(50,reg.predict(hx)))),
                selected_cohort_diagnostic=dict(cost=metrics(cc,cp),
                                                replay_25k=replay(cohort,ordering,25000,use_success=False)),
                note='Training uses stored attempts only. Four additional features selected on the same '
                     'group-CV folds, so CV is exploratory. Holdout and selected cohort are previously '
                     'inspected and diagnostic. Proxy billing may differ from local weighted tokens.')
    (REPORT/'catboost-instruction-training.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(report),flush=True)


if __name__=='__main__':main()
