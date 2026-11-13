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
RUN pip install --no-cache-dir --no-deps catboost==1.2.10 graphviz==0.21 \
    plotly==7.1.0 scipy==1.18.1 six==1.17.0 narwhals==2.28.0
# Final config: the proven 18-feature CatBoost cost predictor with greedy
# reward/cost ordering. The proxy controls the total budget; BUDGET is passed by the runner.
ENV QUEUE=1 QUEUE_POLICY=greedy PREDICTOR=catboost_large QUEUE_USE_SUCCESS=0 SCORE_ALPHA=1 TIGHT_CAPS=1 SEARCH_PROGRESS=entity STAY_INSIDE=1
# Measured on pool200 at 50k, 3 runs each: 519 [479..541] points against 442 [430..450] without them.
# IMPOSSIBLE_PROMPT=1 was measured too (482) and stays off.
ENV PROGRESS_STRICT=1 CODING_PRECHECK=1 SHELL_EXTRA=1
# The teammate's gap facts and nudge on top of the three flags above, same set and budget, 3 runs each:
# 619 [607..633] points against 503 [461..548]. IMPOSSIBLE_RULES=1 on top of that gave 497 and stays off,
# as does SHELL_FIX (covered by SHELL_EXTRA). See docs/impossible-combined-2026-11-13.md.
ENV PRECHECK=1 IMPOSSIBLE_NUDGE=1

# Frozen CatBoost models and the MiniLM fallback encoder are stored in the repository.
# The build verifies their feature count and encoder hashes.
COPY predictors/*.json predictors/
COPY predictors/encoder/ predictors/encoder/
COPY predictors/catboost_large_success.cbm predictors/catboost_large_cost.cbm predictors/
RUN python -c "import hashlib,json;from pathlib import Path;e=Path('/app/predictors/encoder');m=json.loads((e/'provenance.json').read_text());bad=[n for n,h in m['files'].items() if hashlib.sha256((e/n).read_bytes()).hexdigest()!=h];assert not bad,bad"
RUN python -c "from catboost import CatBoostClassifier,CatBoostRegressor;from pathlib import Path;p=Path('/app/predictors');a=CatBoostClassifier();a.load_model(str(p/'catboost_large_success.cbm'));b=CatBoostRegressor();b.load_model(str(p/'catboost_large_cost.cbm'));assert len(a.feature_names_)==len(b.feature_names_)==18"

COPY run_agent.py ./
COPY runtime/ runtime/
COPY evaluation/ evaluation/
