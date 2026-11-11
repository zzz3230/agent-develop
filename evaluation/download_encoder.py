"""Build-time only: fetch a pinned small INT8 encoder; never used by the contest runtime."""
import hashlib
import json
from pathlib import Path
import shutil
from huggingface_hub import HfApi, hf_hub_download

MODEL='sentence-transformers/all-MiniLM-L6-v2'
REVISION='1110a243fdf4706b3f48f1d95db1a4f5529b4d41'
DEST=Path(__file__).resolve().parents[1]/'predictors'/'encoder'

if __name__=='__main__':
    info=HfApi().model_info(MODEL,revision=REVISION)
    revision=info.sha
    files=[x.rfilename for x in info.siblings]
    preferred='onnx/model_quint8_avx2.onnx'
    if preferred not in files: raise ValueError('Expected quantized artifact missing; review model revision')
    DEST.mkdir(parents=True,exist_ok=True)
    hashes={}
    for source,target in [(preferred,'model.onnx'),('tokenizer.json','tokenizer.json')]:
        path=Path(hf_hub_download(MODEL,source,revision=revision))
        shutil.copyfile(path,DEST/target)
        hashes[target]=hashlib.sha256(path.read_bytes()).hexdigest()
    (DEST/'provenance.json').write_text(json.dumps(dict(model=MODEL,revision=revision,files=hashes),indent=2),encoding='utf-8')
    print(json.dumps(dict(revision=revision,bytes=sum(p.stat().st_size for p in DEST.iterdir()))))
