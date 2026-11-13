"""Full 200-task, 50k local-budget trial of selected extended features."""
import hashlib
import json

from evaluation.compare_pool_predictors import summarize
from evaluation.quality_dataset import ROOT, dump, input_hash
from evaluation.run_image import image_id, run

PAIRED=ROOT/'benchmark-runs/best-vs-reward-latest-200-50k'
SUITE=ROOT/'benchmark-runs/planner-200-eval-101-v2'
ORDER=ROOT/'benchmark-runs/best-vs-reward-200-50k/reward-order'
OUT=ROOT/'benchmark-runs/catboost-instruction-full-200-50k'
IMAGE='agent-develop:catboost-instruction'


def main():
    original=json.loads((PAIRED/'protocol.json').read_text(encoding='utf-8'))
    assert original['reward_order_sha256']==input_hash(ORDER)
    original_env=json.loads((PAIRED/'best_predictor/run.json').read_text(encoding='utf-8'))['env']
    assert original_env['QUEUE_POLICY']=='greedy' and original_env['QUEUE_USE_SUCCESS']=='0'
    env={**original_env,'PREDICTOR':'catboost_instruction'}
    models={name:hashlib.sha256((ROOT/'predictors'/('catboost_instruction_'+name+'.cbm')).read_bytes()).hexdigest()
            for name in ('success','cost')}
    protocol=dict(image=IMAGE,image_id=image_id(IMAGE),input_sha256=input_hash(ORDER),
                  budget=50000,env=env,model_hashes=models,
                  training_report='docs/results/quality-minilm-v1/catboost-instruction-training.json',
                  note='One real proxy run, same latest agent and workload as CatBoost-large greedy and reward-only. '
                       'Local weighted-token limit may differ from proxy billing.')
    OUT.mkdir(parents=True,exist_ok=True)
    path=OUT/'protocol.json'
    if path.exists():assert json.loads(path.read_text(encoding='utf-8'))==protocol
    else:dump(path,protocol)
    target=OUT/'trial'
    if not (target/'graded.json').exists():
        run(IMAGE,ORDER,target,env=env,hard_budget=50000,wall_limit=3600,references=SUITE,quiet=True)
    row=summarize(target)
    assert row['exit_code'] in (0,137) and row['spent']>=50000
    dump(OUT/'result.json',row)
    dump(ROOT/'docs/results/quality-minilm-v1/catboost-instruction-full-result.json',
         dict(result=row,protocol=protocol))
    print(json.dumps(row,indent=2),flush=True)


if __name__=='__main__':main()
