# Enterprise Acceptance Matrix

This file tracks the concrete evidence required before LaserClaw can be called enterprise-ready.

## Verified Locally

| Gate | Command / Evidence | Current Status |
|---|---|---|
| Backend regression tests | `cd backend; py -m pytest tests -q` | Passed: `321 passed, 2 skipped` |
| Backend lint | `py -m ruff check backend` | Passed |
| Frontend lint | `cd frontend; npm run lint` | Passed |
| Frontend production build | `cd frontend; npm run build` | Passed |
| SQLite migration from empty DB | `DATABASE_URL=sqlite:///./_tmp_migration_check.db py -m alembic upgrade head` | Passed: chain reaches `20260730_0009` |
| Upgrade of an existing `create_all` database | `tests/test_schema_upgrade.py` | Passed: every model column and index restored on an aged DB, pre-existing rows preserved; NOT NULL columns reported rather than faked |
| Script syntax | `py -m py_compile backend/scripts/*.py` for eval/import scripts | Passed |
| API auth dependency audit | `cd backend; py scripts\audit_endpoint_acl.py --fail-on-findings` | Passed: all `/api/*` routes require a principal dependency |
| Synthetic retrieval backend benchmark | `cd backend; py scripts\benchmark_retrieval_backends.py --backends sql_json,chroma --repeats 10 --top-k 5` | Available; produces `docs/benchmarks/latest_retrieval_backends.json` |
| Synthetic generation latency benchmark | `cd backend; py scripts\benchmark_generation_latency.py --repeats 3` | Available; produces `docs/benchmarks/latest_generation_latency.json` |
| Chroma dense retrieval path | `tests/test_vector_store_chroma.py::test_chroma_backend_retrieves_dense_embeddings` | Passed with deterministic dense embedding |
| Reranker enabled path | `tests/test_reranking.py::test_sentence_transformers_reranker_reorders_with_fake_model` | Passed with deterministic cross-encoder stub |
| ACL/RAG leakage tests | `tests/test_acl.py` | Passed |
| Negative RAG eval metrics | `tests/test_rag_eval_metrics.py` | Passed |
| Eval JSONL schema and private path guard | `tests/test_rag_eval_metrics.py` | Passed |
| Authorized eval threshold gate | `tests/test_rag_eval_metrics.py::test_eval_acceptance_thresholds_report_failures` and `scripts/eval_authorized_rag.py --min-*` | Passed |
| Final acceptance audit wiring | `tests/test_final_acceptance.py`, `scripts/final_acceptance_audit.py` syntax check, and `--skip-local` external-gate failure mode | Passed |
| Score/margin abstention policy | `tests/test_knowledge_agent.py::test_confidence_rejects_ambiguous_low_margin_results` | Passed |
| Public eval dataset format | `load_jsonl_dataset("../docs/evals/examples/rag_eval_synthetic.jsonl")` | Passed by local acceptance script |
| Docker Compose startup | `docker compose up -d`, `/health`, frontend HTTP 200, `docker compose ps` | Passed after Docker Desktop was started |
| PostgreSQL/pgvector integration | `RUN_PGVECTOR_TESTS=1 py -m pytest tests/integration -q` against live pgvector DB | Passed: `2 passed` |
| Docker image build | `docker compose build` | Passed for backend and frontend |
| One-command local acceptance | `cd backend; py scripts\acceptance_check.py` | Passed: backend tests, SQLite migration, script syntax, public eval JSONL, frontend build |
| Open-source license | `LICENSE` | MIT License present |

## Requires External Runtime

| Gate | Command / Evidence | Status |
|---|---|---|
| Remote GitHub Actions | `.github/workflows/ci.yml` green on hosted repository | Requires push/PR on GitHub |
| Authorized private-document eval | `py scripts\eval_authorized_rag.py --dataset ..\docs\evals\private\rag_eval_authorized_holdout.jsonl --min-positive-hit-rate 0.85 --min-negative-rejection-rate 0.90` | Requires permissioned private dataset not committed to Git; command now exits non-zero if thresholds fail |

## One-Command Local Check

```powershell
cd backend
py scripts\acceptance_check.py
```

This runs backend lint, backend tests, SQLite migrations, eval/import/benchmark script syntax checks, API auth dependency audit, frontend lint, and the frontend build.
It also validates the public synthetic eval JSONL example.
CI also runs the backend acceptance extras with `--skip-tests --skip-frontend` so script syntax, SQLite migrations, endpoint auth audit, and public eval JSONL validation are covered remotely.

## V1.0 Performance Evidence Commands

These commands produce reproducible synthetic reports. They are release evidence for benchmark wiring and regressions, not proof of performance on private lab corpora.

```powershell
cd backend
py scripts\benchmark_retrieval_backends.py --backends sql_json,chroma --repeats 10 --top-k 5
py scripts\benchmark_generation_latency.py --repeats 3
```

For `pgvector`, run the retrieval benchmark in an environment where `DATABASE_URL` points at PostgreSQL with pgvector enabled:

```powershell
cd backend
py scripts\benchmark_retrieval_backends.py --backends pgvector --repeats 10 --top-k 5
```

## Final Audit Command

```powershell
cd backend
py scripts\final_acceptance_audit.py
```

This command runs local acceptance, checks the latest hosted GitHub Actions `CI` workflow through the GitHub API, and validates `docs/evals/private/last_report.json`. It exits non-zero until both external-runtime gates have real passing evidence.

## Completion Criteria

LaserClaw is fully accepted only when every verified-local gate stays green and every external-runtime gate has current evidence from the target environment.
