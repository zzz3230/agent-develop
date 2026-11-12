"""Training-only matrices; cache embeddings without loading any control inputs."""
import hashlib
import inspect
import json
import numpy as np

from runtime.predictor import features,Encoder
from evaluation.predictor_experiment import ROOT,OUT


def embedded(rows,strong):
    directory=ROOT/'predictors'/('encoder-strong' if strong else 'encoder')
    texts=[r['task'].instruction for r in rows]
    key=hashlib.sha256(json.dumps(texts).encode()+inspect.getsource(Encoder).encode()+
        (directory/'provenance.json').read_bytes()+((directory/'encoding.json').read_bytes() if (directory/'encoding.json').exists() else b'')).hexdigest()
    cache=OUT/('training-embeddings-'+key+'.npy')
    if cache.exists():return np.load(cache,allow_pickle=False)
    values=Encoder(directory).encode(texts)
    np.save(cache,values,allow_pickle=False)
    return values


def matrix(rows,mode):
    if mode=='strong_embedding':return embedded(rows,True)
    numeric=np.asarray([features(r['task'],keywords=mode not in ('structural','bge_structural')) for r in rows])
    if mode in ('embedding','bge_structural','bge_keywords'):
        return np.hstack([numeric,embedded(rows,mode!='embedding')])
    return numeric
