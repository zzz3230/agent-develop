"""Two predictor ablations, then tuned-alpha and knapsack, one 6000-token run each."""
import json
import os
import subprocess
import sys

from evaluation.predictor_experiment import OUT,dump
from evaluation.run_image import run

DIRECTORY=OUT/'scarce-6000'
IMAGE='agent-develop:predictor-policies'


def trial(label,mode,policy='greedy',alpha=1):
    target=DIRECTORY/label
    if not (target/'graded.json').exists():
        run(IMAGE,OUT/'control-order-101',target,
            env={'PREDICTOR':mode,'QUEUE_POLICY':policy,'SCORE_ALPHA':str(alpha),'QUEUE':'1','RETRY':'0',
                 'BUDGET':'6000','ENFORCE_BUDGET':'1'},hard_budget=6000,wall_limit=3600,
            references=OUT/'control',with_probe=False,quiet=True)
    grade=json.loads((target/'graded.json').read_text(encoding='utf-8'))
    info=json.loads((target/'run.json').read_text(encoding='utf-8'))
    row=dict(label=label,mode=mode,policy=policy,alpha=alpha,points=grade['total']['points'],
        correct=grade['total']['correct'],spent=grade['spent'],seconds=info['wall_seconds'])
    print('SCARCE '+json.dumps(row),flush=True)
    return row


def main():
    rows=[]
    for mode in ('bge_structural','bge_keywords'):
        rows.append(trial(mode,mode));dump(DIRECTORY/'comparison.json',rows)
    best=max(rows,key=lambda r:r['points']) # stable: keyword-free wins an exact tie
    dump(DIRECTORY/'selection.json',dict(mode=best['mode'],basis=rows,
        criterion='Highest single-seed points at 6000; keyword-free wins ties. Known controls, exploratory selection.'))
    env=dict(os.environ);env.pop('LLM_API_KEY',None)
    subprocess.run([os.environ.get('PREDICTOR_TRAIN_PYTHON',sys.executable),'-m','evaluation.tune_planning',
        '--mode',best['mode'],'--scarce'],check=True,env=env)
    tuning=json.loads((OUT/'planning-tuning-6000.json').read_text(encoding='utf-8'))
    alpha=tuning['scenarios'][0]['selected_alpha']
    rows.append(trial('tuned-alpha',best['mode'],alpha=alpha));dump(DIRECTORY/'comparison.json',rows)
    rows.append(trial('knapsack',best['mode'],policy='knapsack'));dump(DIRECTORY/'comparison.json',rows)


if __name__=='__main__':main()
