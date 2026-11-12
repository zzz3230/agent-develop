"""Predeclared selection: same single seed for every head; prefer simpler ties."""
import json
from evaluation.predictor_experiment import ROOT,OUT,dump


def select():
    previous=json.loads((ROOT/'docs/results/offline-predictors-v2/results.json').read_text(encoding='utf-8'))
    candidates=[dict(mode=r['mode'],points=r['points']) for r in previous['runs'] if r['mode']!='baseline']
    keywords=json.loads((OUT/'keywords-101/graded.json').read_text(encoding='utf-8'))
    candidates.append(dict(mode='bge_keywords',points=keywords['total']['points']))
    simplicity=['structural','numeric','embedding','strong_embedding','bge_structural','bge_keywords']
    best=max(candidates,key=lambda r:(r['points'],-simplicity.index(r['mode'])))
    result=dict(selected=best['mode'],candidates=candidates,seed=101,
        criterion='Maximum points on identical single-seed controls; simpler predictor wins ties. Exploratory model selection on known controls.')
    dump(OUT/'predictor-selection.json',result)
    return result


if __name__=='__main__':print(json.dumps(select(),indent=2))
