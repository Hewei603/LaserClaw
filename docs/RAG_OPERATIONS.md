# RAG Operations and Evaluation

LaserClaw supports a deterministic local retriever and optional production-oriented vector retrieval paths.

## Retrieval Modes

### SQL JSON

Default local mode:

```env
EMBEDDING_PROVIDER=local
RETRIEVAL_BACKEND=sql_json
RERANKER_PROVIDER=none
```

Use this for deterministic tests and offline demos.

### Chroma

Install optional ML dependencies before using local sentence-transformers models:

```powershell
cd backend
py -m pip install -r requirements-ml.txt
```

```env
EMBEDDING_PROVIDER=sentence_transformers
EMBEDDING_MODEL=BAAI/bge-small-en-v1.5
RETRIEVAL_BACKEND=chroma
VECTOR_STORE_DIR=./backend/vector_store
PGVECTOR_DIMENSION=384
```

Reindex after changing embedding provider or model:

```powershell
cd backend
py scripts\reindex_all_sources.py
```

Acceptance:

- `POST /api/knowledge/search` returns citation-ready results.
- Logs show Chroma query activity.
- `backend/vector_store` persists across restarts when configured as a volume.

### pgvector

Docker Compose uses `pgvector/pgvector:pg15`.

Recommended env for the included migration:

```env
DATABASE_URL=postgresql://laserclaw:laserclaw123@localhost:5432/laserclaw
EMBEDDING_PROVIDER=sentence_transformers
EMBEDDING_MODEL=BAAI/bge-small-en-v1.5
RETRIEVAL_BACKEND=pgvector
PGVECTOR_DIMENSION=384
```

Important: the migration creates `embedding vector(384)`. If you switch to a different embedding dimension, update `PGVECTOR_DIMENSION` and rebuild the pgvector table/migration for that dimension.

Run integration tests:

```powershell
$env:RUN_PGVECTOR_TESTS="1"
$env:DATABASE_URL="postgresql://laserclaw:laserclaw123@localhost:5432/laserclaw"
$env:RETRIEVAL_BACKEND="pgvector"
$env:EMBEDDING_PROVIDER="sentence_transformers"
$env:EMBEDDING_MODEL="BAAI/bge-small-en-v1.5"
cd backend
py -m pytest tests\integration -q
```

Acceptance:

- Alembic creates `knowledge_chunk_vectors`.
- Reindex writes dense vectors.
- Integration tests pass against a live PostgreSQL/pgvector database.

## Reranker

Default:

```env
RERANKER_PROVIDER=none
```

Enable local cross-encoder reranking:

```powershell
cd backend
py -m pip install -r requirements-ml.txt
```

```env
RERANKER_PROVIDER=sentence_transformers
RERANKER_MODEL=cross-encoder/ms-marco-MiniLM-L-6-v2
RERANKER_TOP_K=20
RERANKER_WEIGHT=0.65
```

Acceptance:

- Reranker is applied only to bounded first-stage candidates.
- `RetrievalResult` rows still store final top-k scores and ranks.
- Latency remains acceptable for the configured `RERANKER_TOP_K`.

## Authorized Document Import

Put permissioned documents in:

```text
backend/uploads/authorized_lab_docs/
```

Import:

```powershell
cd backend
py scripts\index_authorized_docs.py
```

The script marks imported sources as `approved` and `authorized_eval=true`. Do not commit these documents.

## JSONL Eval Format

Store private eval datasets under:

```text
docs/evals/private/
```

A public synthetic example is available at:

```text
docs/evals/examples/rag_eval_synthetic.jsonl
```

Use it to validate loader/schema wiring. It is not evidence for real lab retrieval quality.

Example row:

```json
{"id":"safety-001","query":"What PPE is required before alignment?","should_answer":true,"expected_source_title_contains":"safety","expected_terms":["PPE","OD"]}
```

Negative row:

```json
{"id":"neg-001","query":"coffee machine warranty policy","should_answer":false}
```

Run CLI eval:

```powershell
cd backend
py scripts\eval_authorized_rag.py --dataset ..\docs\evals\private\rag_eval_authorized.jsonl --top-k 5 --output ..\docs\evals\private\last_report.json
```

Run it as a release gate by adding thresholds:

```powershell
cd backend
py scripts\eval_authorized_rag.py `
  --dataset ..\docs\evals\private\rag_eval_authorized_holdout.jsonl `
  --top-k 5 `
  --min-positive-hit-rate 0.85 `
  --min-negative-rejection-rate 0.90 `
  --output ..\docs\evals\private\last_report.json
```

Validate the public example format:

```powershell
cd backend
py -c "from app.evals.datasets import load_jsonl_dataset; print(len(load_jsonl_dataset('../docs/evals/examples/rag_eval_synthetic.jsonl')))"
```

Tune thresholds:

```powershell
cd backend
py scripts\tune_retrieval_thresholds.py --dataset ..\docs\evals\private\rag_eval_authorized.jsonl --top-k 5
```

Run API eval:

```http
POST /api/evals/rag/private-dataset?dataset_path=docs/evals/private/rag_eval_authorized.jsonl&top_k=5
```

Acceptance:

- Positive samples report source/title/term hit and MRR.
- Negative samples report no-answer rejection.
- Score and top1-top2 margin thresholds are configurable through `RETRIEVAL_MIN_SCORE`, `RETRIEVAL_LOW_CONFIDENCE_SCORE`, `RETRIEVAL_ANSWER_MARGIN_MIN`, and `RETRIEVAL_NEGATIVE_POLICY`.
- CLI threshold gates exit non-zero when a private holdout set falls below the configured minimum positive hit rate, negative rejection rate, or mean MRR.
- Results are persisted in `rag_eval_runs`.
- Private datasets and reports remain ignored by Git.
