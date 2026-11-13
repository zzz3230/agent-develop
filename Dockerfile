FROM python:3.12-slim@sha256:5e2bdb1b0d542d5039cffb8181c65930093949194a65c365dfb1b0fe13a4fa5b

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

COPY requirements.lock .
RUN pip install --no-deps -r requirements.lock

# Task predictor: ONNX runtime for the MiniLM encoder. A separate layer keeps the
# dependency layer above cached; versions are pinned like the rest.
RUN pip install --no-deps onnxruntime==1.22.1 coloredlogs==15.0.1 humanfriendly==10.0 \
    flatbuffers==25.12.19 sympy==1.14.0 mpmath==1.3.0
ENV OMP_NUM_THREADS=2 OPENBLAS_NUM_THREADS=2 TOKENIZERS_PARALLELISM=false
# Final config (night run 2026-11-13, budget covers ~30% of tasks): MiniLM queue predictor plus
# the guards against expensive impossible tasks. Any of these can be overridden with -e.
ENV QUEUE=1 QUEUE_POLICY=greedy PREDICTOR=embedding TIGHT_CAPS=1 SEARCH_PROGRESS=entity STAY_INSIDE=1
# Measured on pool200 at 50k, 3 runs each: 519 [479..541] points against 442 [430..450] without them.
# IMPOSSIBLE_PROMPT=1 was measured too (482) and stays off.
ENV PROGRESS_STRICT=1 CODING_PRECHECK=1 SHELL_EXTRA=1

# Predictor coefficients and the MiniLM encoder are stored in the repository: nothing is
# downloaded at build or run time. The build fails if the encoder does not match its hashes.
COPY predictors/*.json predictors/
COPY predictors/encoder/ predictors/encoder/
RUN python -c "import hashlib,json;from pathlib import Path;e=Path('/app/predictors/encoder');m=json.loads((e/'provenance.json').read_text());bad=[n for n,h in m['files'].items() if hashlib.sha256((e/n).read_bytes()).hexdigest()!=h];assert not bad,bad"

COPY run_agent.py ./
COPY runtime/ runtime/
COPY evaluation/ evaluation/
