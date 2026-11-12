"""One fixed 200-task, 50k trial per frozen predictor, then best with knapsack."""
import argparse
import hashlib
import json
from pathlib import Path
import random

from evaluation.run_image import run

MODES=('numeric','embedding','structural','strong_embedding','bge_structural','bge_keywords')
BUDGET=50000
IMAGE='agent-develop:predictor-policies'
AGENT_COMMIT='f8e23acab8083a1ae7172c05b6033b83c22ee761'


def dump(path,value):
    path.write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')


def summarize(target):
    grade=json.loads((target/'graded.json').read_text(encoding='utf-8'))
    info=json.loads((target/'run.json').read_text(encoding='utf-8'))
    spent=0.;eligible=set();completed=set();calls=[]
    for line in (target/'harness'/'trajectory.jsonl').read_text(encoding='utf-8').splitlines():
        row=json.loads(line)
        if row['event']=='llm_call':
            spent+=row['cost'];calls.append(row)
        elif row['event']=='outcome':
            completed.add(row['task'])
            if spent<=BUDGET+1e-6:eligible.add(row['task'])
    return dict(mode=info['env']['PREDICTOR'],policy=info['env']['QUEUE_POLICY'],
        points=grade['total']['points'],correct=grade['total']['correct'],
        strict_points=sum(r['points'] for r in grade['rows'] if r['id'] in eligible),
        strict_correct=sum(r['correct'] for r in grade['rows'] if r['id'] in eligible),
        possible=grade['total']['possible'],completed=len(completed),
        spent=grade['spent'],seconds=info['wall_seconds'],stopped_by=info['stopped_by'],
        finish=info['finish'],exit_code=info['exit_code'],calls=len(calls),
        input=sum(r['input'] for r in calls),output=sum(r['output'] for r in calls),
        estimated_calls=sum(r.get('estimated',False) for r in calls))


def experiment(suite,out):
    out.mkdir(parents=True,exist_ok=True)
    manifest=json.loads((suite/'manifest.json').read_text(encoding='utf-8'))
    assert len(manifest['tasks'])==200,'Expected the frozen 200-task workload'
    order=['baseline',*MODES];random.Random(101).shuffle(order)
    protocol=dict(tasks=200,budget=BUDGET,image=IMAGE,agent_commit=AGENT_COMMIT,
        input_sha256=manifest['input_sha256'],selection_seed=manifest['selection_seed'],
        reward_seed=manifest['reward_seed'],order=order,repeats=1,score_alpha=1,
        selection='Highest strict_points among six trained predictors; lower spend breaks ties; fixed mode order last.',
        caveat='Exploratory selection and final policy comparison share the same known evaluation workload.',
        model_hashes={m:hashlib.sha256((Path('predictors')/(m+'.json')).read_bytes()).hexdigest() for m in MODES})
    protocol_path=out/'protocol.json'
    if protocol_path.exists():
        assert json.loads(protocol_path.read_text(encoding='utf-8'))==protocol,'Protocol changed'
    else:dump(protocol_path,protocol)
    rows=[]

    def trial(mode,policy):
        target=out/(mode+'-'+policy)
        if not (target/'graded.json').exists():
            print('START '+mode+' '+policy,flush=True)
            run(IMAGE,suite/'input',target,
                env={'PREDICTOR':mode,'QUEUE_POLICY':policy,'SCORE_ALPHA':'1',
                     'QUEUE':'1','RETRY':'0','BUDGET':str(BUDGET),'ENFORCE_BUDGET':'1'},
                hard_budget=BUDGET,wall_limit=3600,references=suite,
                commit=AGENT_COMMIT,quiet=True)
        row=summarize(target)
        if row['exit_code'] not in (0,137):
            raise RuntimeError('Infrastructure/agent error, not a valid trial: '+str(target))
        if row['stopped_by']=='wall_limit':
            raise RuntimeError('Time-limited trial; cannot select a winner at 50k')
        if row['spent']<BUDGET and row['completed']<200:
            raise RuntimeError('Incomplete trial below token limit: '+str(target))
        print('RESULT '+json.dumps(row),flush=True)
        rows.append(row);dump(out/'comparison.json',rows)
        return row

    for mode in order:trial(mode,'greedy')
    trained=[r for r in rows if r['mode'] in MODES]
    best=max(trained,key=lambda r:(r['strict_points'],-r['spent'],-MODES.index(r['mode'])))
    dump(out/'selection.json',dict(best=best,criterion=protocol['selection']))
    trial(best['mode'],'knapsack')


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--suite',type=Path,default=Path('benchmark-runs/planner-200-eval-101-v2'))
    parser.add_argument('--out',type=Path,default=Path('benchmark-runs/pool200-budget50000'))
    args=parser.parse_args();experiment(args.suite,args.out)
