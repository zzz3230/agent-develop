"""Choose a small bounded feature subset using stored labels and group CV."""
import json

import numpy as np
from catboost import CatBoostRegressor
from sklearn.model_selection import GroupKFold

from evaluation.catboost_cost_ablation import metrics
from evaluation.train_catboost_large import REPORT, load_training_rows
from runtime.predictor import features

BASE = tuple(range(18))
GROUPS = dict(instruction=(18,19,20,21), files_and_code=(22,23,24),
              csv=(25,26,28), identifiers=(27,))
SUBSETS = dict(base=BASE,
               instruction=BASE+GROUPS['instruction'],
               files_and_code=BASE+GROUPS['files_and_code'],
               csv=BASE+GROUPS['csv'],
               identifiers=BASE+GROUPS['identifiers'],
               instruction_csv=BASE+GROUPS['instruction']+GROUPS['csv'],
               files_csv=BASE+GROUPS['files_and_code']+GROUPS['csv'],
               all=tuple(range(29)))


def main():
    rows,_,_,held=load_training_rows()
    x=np.asarray([features(r['task'],keywords=False,extended=True) for r in rows],dtype=np.float32)
    y=np.asarray([r['cost'] for r in rows])
    groups=[r['group'] for r in rows]
    assert not set(groups)&held
    folds=list(GroupKFold(n_splits=5).split(x,y,groups))
    result={}
    for name,indices in SUBSETS.items():
        oof=np.zeros(len(y))
        for train,test in folds:
            model=CatBoostRegressor(depth=3,iterations=150,l2_leaf_reg=10,random_seed=71,
                                    verbose=False,thread_count=2,allow_writing_files=False,
                                    loss_function='MAE').fit(x[train][:,indices],y[train])
            oof[test]=np.maximum(50,model.predict(x[test][:,indices]))
        result[name]=dict(indices=indices,group_cv=metrics(y,oof))
        print(name,round(result[name]['group_cv']['mae'],2),
              round(result[name]['group_cv']['spearman'],3),flush=True)
    selected=min(result,key=lambda n:(result[n]['group_cv']['mae'],
                                      -result[n]['group_cv']['spearman']))
    report=dict(rows=len(rows),groups=len(set(groups)),selected=selected,subsets=result,
                note='All labels are stored attempts. Subset selected on grouped CV; these CV '
                     'numbers are exploratory because subsets were compared on the same folds.')
    (REPORT/'catboost-feature-subsets.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
    print('SELECTED',selected,flush=True)


if __name__=='__main__':main()
