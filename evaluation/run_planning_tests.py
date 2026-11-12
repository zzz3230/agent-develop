"""One real-proxy test per policy after train-only alpha selection is frozen."""
import json
from evaluation.predictor_experiment import OUT,dump
from evaluation.run_image import run


def main():
    tuning=json.loads((OUT/'planning-tuning.json').read_text(encoding='utf-8'))
    selected=json.loads((OUT/'predictor-selection.json').read_text(encoding='utf-8'))
    assert tuning['mode']==selected['selected']
    alpha=next(s['selected_alpha'] for s in tuning['scenarios'] if s['budget']==12000)
    results=[]
    for label,policy,exponent in [('tuned-alpha','greedy',alpha),('knapsack','knapsack',1)]:
        target=OUT/(label+'-101')
        if not (target/'graded.json').exists():
            run('agent-develop:predictor-policies',OUT/'control-order-101',target,
                env={'PREDICTOR':tuning['mode'],'SCORE_ALPHA':str(exponent),'QUEUE_POLICY':policy,'QUEUE':'1','RETRY':'0',
                     'BUDGET':'12000','ENFORCE_BUDGET':'1'},hard_budget=12000,wall_limit=3600,
                references=OUT/'control',with_probe=False,quiet=True)
        grade=json.loads((target/'graded.json').read_text(encoding='utf-8'))
        info=json.loads((target/'run.json').read_text(encoding='utf-8'))
        row=dict(policy=policy,alpha=exponent,mode=tuning['mode'],points=grade['total']['points'],
                 correct=grade['total']['correct'],spent=grade['spent'],seconds=info['wall_seconds'])
        results.append(row);dump(OUT/'planning-live.json',results)
        print('LIVE_POLICY '+json.dumps(row),flush=True)


if __name__=='__main__':main()
