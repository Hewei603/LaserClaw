# LaserClaw Resume Project Write-up

Generated from local benchmark evidence on 2026-06-11.

All RAG accuracy and latency metrics below are based on synthetic benchmark documents under `docs/evals/synthetic_laser_docs/`. They are suitable for describing reproducible engineering evaluation, but should not be presented as production or real-lab performance.

## Evidence Snapshot

| Area | Evidence |
|---|---|
| Backend quality gate | `161 passed, 2 skipped` via `py scripts\acceptance_check.py` |
| Backend lint | Ruff passed |
| Frontend quality gate | ESLint and Vite production build passed |
| API auth coverage | 70 `/api/*` routes audited, 0 findings |
| Synthetic RAG corpus | 3 documents, 5 chunks, 10-query benchmark, 100 retrieval executions |
| Synthetic RAG result | Recall@1/3/5 = 100%, MRR = 1.000 |
| Synthetic RAG latency | P50 7.00 ms, P95 9.43 ms, mean 10.68 ms |
| Synthetic indexing throughput | 470.53 chunks/s over the small synthetic corpus |
| Retrieval backend comparison | `sql_json` and Chroma both passed 40 synthetic retrieval executions |
| `sql_json` backend latency | P50 2.95 ms, P95 3.74 ms |
| Chroma backend latency | P50 2.75 ms, P95 3.91 ms |
| Structured generation benchmark | plan / troubleshooting / report / ReZonator all 0 failures |
| Structured generation schema pass | 100% on 12 mock-provider synthetic runs |

Docker / pgvector smoke checks were not counted in this snapshot because Docker Desktop was not running locally during measurement.

## Resume Version - AI Agent / RAG Engineer

**LaserClaw | Local-first RAG Agent Workspace for Laser Experiment Workflows**
Tech stack: Python, FastAPI, React, SQLAlchemy, Alembic, SQLite/PostgreSQL, pgvector, Chroma, Docker, RAG, Tool Calling, OpenAI-compatible API, Anthropic API, Ruff, ESLint

- Designed and implemented a local-first RAG Agent workspace for laser experiment workflows, covering experiment case management, global/case-specific knowledge indexing, Agent chat, structured artifact generation, citations, trace persistence, ACL, audit logs, and Dockerized deployment.
- Built a two-tier RAG pipeline over global lab knowledge and case-specific evidence, with chunking, deterministic local embeddings, hybrid lexical/vector scoring, Chroma/pgvector adapter paths, citation persistence, confidence labels, and retrieval-run audit records.
- Implemented a tool-calling Agent workflow that routes user requests into chat, experiment plan, troubleshooting, report, ReZonator draft, and case module tasks; persisted `AgentTask`, `AgentStep`, `AgentToolCall`, `RetrievalRun`, and `GeneratedContent` for reproducible review.
- Added project-level ACL across cases, knowledge search, attachments, generation, Agent tasks, case modules, and bundle export; built an endpoint audit script that verified 70 `/api/*` routes with 0 missing principal dependencies.
- Established reproducible local quality gates with Ruff, pytest, Alembic migration checks, endpoint ACL audit, ESLint, Vite production build, and synthetic benchmark scripts; latest local run passed 161 backend tests and frontend lint/build.
- Created a synthetic laser-domain RAG benchmark with 3 documents and 10 queries; ran 100 retrieval executions with Recall@1/3/5 = 100%, MRR = 1.000, and P95 retrieval latency of 9.43 ms under deterministic local settings.

## Resume Version - Backend / Full-stack Engineer

**LaserClaw | Laser Experiment RAG Agent Platform**
Tech stack: FastAPI, React, SQLAlchemy, Alembic, SQLite/PostgreSQL, Chroma, pgvector, Docker, pytest, Ruff, ESLint

- Developed a full-stack experiment workflow platform with FastAPI backend and React frontend, supporting case management, file attachments, knowledge indexing, Agent chat, generated reports, module workflows, permission checks, and case bundle export.
- Designed SQLAlchemy data models and Alembic migrations for cases, attachments, knowledge sources/chunks, retrieval runs/results, Agent traces, generated content, collaboration entities, audit logs, and prompt/workflow versions.
- Implemented release-oriented acceptance checks covering backend lint/tests, SQLite migrations, script syntax, API auth dependency audit, frontend lint, and production build; latest local gate passed 161 tests with 0 ACL audit findings.
- Built benchmark tooling for retrieval backends and structured generation latency; synthetic benchmark results showed both `sql_json` and Chroma retrieval paths passing 40 executions with sub-4 ms P95 latency on the small benchmark corpus.
- Added documentation for deployment, acceptance gates, security expectations, private eval workflow, and benchmark limitations to keep project metrics reproducible and defensible.

## Short Version

Built LaserClaw, a FastAPI + React local-first RAG Agent workspace for laser experiment workflows. The system supports case management, global/case-specific RAG, Agent tool routing, structured plan/troubleshooting/report/ReZonator generation, citations, trace persistence, project-level ACL, audit logs, Docker deployment, and reproducible benchmarks. Latest local gates passed 161 backend tests, Ruff, ESLint, Vite build, SQLite migrations, and an endpoint ACL audit covering 70 `/api/*` routes with 0 findings. On a synthetic laser-domain RAG benchmark, ran 100 retrieval executions with Recall@1/3/5 = 100%, MRR = 1.000, and P95 retrieval latency of 9.43 ms.

## Interview Talking Points

- Two-tier RAG separates lab-wide authoritative knowledge from case-specific attachments and generated artifacts, reducing the chance that local case notes override safety or SOP context.
- Agent output is persisted as structured artifacts with citations and task traces, so generation is auditable rather than a transient chat response.
- ACL is applied before case-specific retrieval and export, which directly addresses RAG data leakage across projects.
- The synthetic benchmark is intentionally marked synthetic. It proves the evaluation harness and regression tracking, while real deployment claims should be re-measured on authorized private documents.
- Current performance numbers are small-corpus local metrics. At larger corpus size, the likely bottlenecks are embedding generation, vector backend indexing, reranking latency, and database/query concurrency.

## Metrics Not To Overclaim

- Do not claim production recall or real lab safety correctness from the synthetic benchmark.
- Do not claim Docker or pgvector smoke success from this run; Docker Desktop was not running.
- Do not claim real LLM latency from the mock-provider generation benchmark.
- Do not claim enterprise identity management; the built-in API-key mode is best described as local/small trusted deployment auth.
