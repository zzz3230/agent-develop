"""Two predefined ablations on the existing controls; training is unchanged."""
import json
from pathlib import Path

from evaluation.predictor_experiment import ROOT,OUT,dump
from evaluation.run_image import run

IMAGE='agent-develop:predictor-extensions'
DIRECTORY=OUT/'extensions'


def main():
    summary=[]
    for repeat,seed in enumerate((101,102,103)):
        modes=['structural','strong_embedding'] if repeat%2==0 else ['strong_embedding','structural']
        for mode in modes:
            out=DIRECTORY/f'{mode}-{seed}'
            if not (out/'graded.json').exists():
                run(IMAGE,OUT/f'control-order-{seed}',out,
                    env={'PREDICTOR':mode,'QUEUE':'1','RETRY':'0','BUDGET':'12000','ENFORCE_BUDGET':'1'},
                    hard_budget=12000,wall_limit=3600,references=OUT/'control',with_probe=False,quiet=True)
            grade=json.loads((out/'graded.json').read_text(encoding='utf-8'))
            info=json.loads((out/'run.json').read_text(encoding='utf-8'))
            row=dict(mode=mode,seed=seed,points=grade['total']['points'],correct=grade['total']['correct'],
                spent=grade['spent'],seconds=info['wall_seconds'])
            summary.append(row);dump(DIRECTORY/'comparison.json',summary)
            print('EXTENSION '+json.dumps(row),flush=True)


if __name__=='__main__': main()
