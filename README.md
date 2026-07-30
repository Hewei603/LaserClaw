# LaserClaw

LaserClaw is a local-first **RAG Agent workspace for laser experiment workflows**. It combines experiment case management, lab knowledge indexing, case-specific evidence retrieval, structured AI artifact generation, persistent Agent traces, and collaboration-oriented governance.

> Safety note: LaserClaw does not control lasers, power supplies, translation stages, interlocks, optical tables, detectors, or any other lab hardware. Generated content is advisory draft material and must be reviewed by qualified personnel.

![LaserClaw screenshot](https://github.com/user-attachments/assets/b8ebb7f4-f980-4671-8722-2ef0913f7f70)

## What It Solves

| Problem | LaserClaw approach |
|---|---|
| Lab knowledge is scattered across manuals, SOPs, notes, and case files | Two-tier RAG over global lab documents and case-specific documents |
| AI answers are hard to audit | Stored retrieval runs, citations, generated artifacts, Agent steps, and tool calls |
| Troubleshooting and reporting are repetitive | Structured generation for plans, troubleshooting and reports, grounded in deterministic physics results |
| Research groups need long-term collaboration | Projects, users, groups, permissions, knowledge governance, versioned prompts/workflows, and case bundles |

## Core Features

- **Case-aware Agent chat** with persistent sessions, linked case data, citations, retrieval confidence, and recent conversation context.
- **Two-tier RAG** over global lab knowledge plus case-specific attachments and generated artifacts.
- **Global knowledge base** for PDFs, TXT, Markdown, CSV, JSON, TSV, and log files.
- **Knowledge governance** with source status, version, owner, reviewer, review time, and reindexing.
- **Tool-calling Agent workflow** for chat, experiment plans, troubleshooting, reports, and deterministic physics/measurement modules.
- **Deterministic physics kernel** (pure numpy): ABCD/Gaussian cavity analysis and design search with a measured thermal-lens margin, thin-film TMM coating evaluation, uniaxial/biaxial phase matching, and power-curve threshold/slope fits with Findlay-Clay and Caird cavity-loss analysis. Experiment plans are generated **around these computed numbers**, not around numbers the model invented.
- **Structured component inventory**: import a lab component workbook (.xlsx), filter by wavelength/function at the coating-spec level, and evaluate candidates parameter by parameter against a requirement spec (usable / must-measure / rejected, with a dominance frontier). Cavity design searches are constrained to mirrors the lab actually owns.
- **Loan and damage tracking**: borrowing reduces *availability* and never the workbook's stock number (which every re-import overwrites), a human damage verdict is stored apart from the parsed one so re-import cannot resurrect a chipped mirror, and borrowed or damaged items drop out of matching with an explicit rejection reason.
- **Printable plans**: cavity design results include a to-scale **layout diagram** (mirror orientation, crystal position, cold-cavity mode envelope and waist); `Ctrl+P` on any case page exports a lab-ready PDF — vector graphics, black on white, navigation and controls hidden.
- **Structured AI artifacts** saved as versioned generated content.
- **Prompt/workflow versioning** for reproducible AI runs.
- **Case bundle export** with manifest, attachments, generated content, and knowledge metadata.
- **Project-level ACL** across cases, knowledge search, attachments, generation, Agent tasks, case modules, and bundle export.
- **RAG evals and benchmarks** for retrieval quality, latency, indexing throughput, and JSON reliability.
- **Retrieval backends** including deterministic `sql_json`, Chroma, pgvector, and optional cross-encoder reranking.
- **Provider support** for MockProvider, OpenAI-compatible Chat Completions (OpenAI, DeepSeek, Qwen/DashScope, Zhipu GLM, Moonshot Kimi), and Anthropic.
- **Bilingual UI** with English and Chinese language switching.

## Architecture

```text
React + Vite frontend
  -> FastAPI backend
      -> Case / attachment / knowledge / generation / agent / collaboration APIs
      -> SQLAlchemy models and Alembic migrations
      -> SQLite locally or PostgreSQL/pgvector in Docker
      -> File uploads and global knowledge documents
      -> RAG ingestion, chunking, embeddings, retrieval, citations
      -> Deterministic physics kernel (ABCD/Gaussian cavity, thin-film TMM,
         phase matching, power-curve fits) - pure numpy, no LLM
      -> Structured component inventory (workbook parsing + parameter-level evaluator)
      -> OpenAI-compatible / Anthropic / Mock provider
      -> Audit logs, usage tracking, Agent traces, generated artifacts
```

## RAG Workflow

```text
Global document / case attachment / generated artifact
  -> text extraction
  -> chunking
  -> embedding
  -> KnowledgeSource + KnowledgeChunk
  -> query-time retrieval
  -> RetrievalRun + RetrievalResult
  -> citation-ready context for chat or artifact generation
```

LaserClaw uses two retrieval tiers:

1. **Global lab knowledge**: safety manuals, SOPs, optical component catalogs, and lab-wide operating rules.
2. **Case knowledge**: case data, attachments, image analysis, prior reports, and generated artifacts linked to the current case.

![LaserClaw RAG screenshot](https://github.com/user-attachments/assets/ffc09e0d-93a4-4259-a07b-c943fbbf4cf9)

## Agent Workflow

```text
User message
  -> create/find chat session
  -> save user message
  -> route intent
  -> build context from chat history, case data, RAG results, citations
  -> chat response or saved Agent task
  -> save assistant message / task / artifact / citations
```

The chat API can auto-route generation requests, and direct task creation is also available through `POST /api/agent/tasks`. Generation requests create an `AgentTask`, build steps, call tools, retrieve evidence, generate an artifact, save it to the case, and store the trace.

## Retrieval Options

The default stack is deterministic and local:

- tokenization: ASCII terms plus Chinese character, bigram, and trigram tokens
- synonym expansion for common safety and optics terms
- section-aware chunking for headings such as `[SAF-PPE]`, `[SAF-SOP]`, `[OPT-MIRROR]`
- section metadata persisted on chunks
- lightweight domain boosts for safety-related and optics-related queries

Production-oriented retrieval options are wired:

- `sql_json`: local fallback over JSON embeddings and lexical scoring
- `chroma`: dense vector retrieval with persisted local Chroma collections
- `pgvector`: PostgreSQL/pgvector retrieval with SQL metadata remaining authoritative
- optional `sentence_transformers` cross-encoder reranker over bounded candidates

Operational setup and acceptance checks are documented in [docs/RAG_OPERATIONS.md](docs/RAG_OPERATIONS.md).

## Current Evaluation Evidence

Every number below is reproducible from this repository with the command next to
it, on the **default local configuration** (`EMBEDDING_PROVIDER=local`,
`RETRIEVAL_BACKEND=sql_json`, `AI_PROVIDER=mock`). Measured 2026-07-26. Each
command writes a JSON report into `docs/benchmarks/`, which is **gitignored** —
those reports can index private lab documents, so regenerate them locally rather
than trusting a committed copy.

The retrieval corpus is **synthetic** — these are not real laboratory policies,
equipment data, or safety training material — and it is small (3 sources, 5
chunks, 10 labelled queries). The retrieval figures therefore say the pipeline
works end to end; they are **not** a claim about production-scale accuracy.

| Check | Result | Reproduce with |
|---|---|---|
| Backend test suite | 317 passed, 2 skipped | `cd backend && py -m pytest -q` |
| Physics kernel vs analytic/literature | included above (TMM cross-checked against the independent `tmm` package to machine precision) | `py -m pytest tests/test_physics_*.py -q` |
| Intent-routing cases | 57 passed | `py -m pytest tests/test_router.py -q` |
| RAG dataset assertions | 8 passed (37-query dataset) | `py -m pytest tests/eval_rag_dataset.py -q` |
| Agent trace completeness | 7 passed | `py -m pytest tests/eval_agent_trace.py -q` |
| API auth dependency audit | 74 `/api/*` routes checked, 0 findings | `py scripts/audit_endpoint_acl.py` |
| Frontend lint/build | Passed | `cd frontend && npm run lint && npm run build` |

Retrieval quality and latency on the synthetic corpus
(report: `docs/benchmarks/resume_metrics_*.json`):

| Metric | Result |
|---|---:|
| Recall@1 | 90.00% |
| Recall@3 | 100.00% |
| Recall@5 | 100.00% |
| MRR | 0.95 |
| Query latency p50 / p95 | 12.7 ms / 14.4 ms |
| Indexing throughput | 103.9 chunks/s |

Reproduce with `py scripts/benchmark_resume_metrics.py --repeats 3 --skip-llm`
(10 labelled queries x 3 repeats = 30 executions, top_k=5).

Structured generation shape and latency, MockProvider
(report: `docs/benchmarks/latest_generation_latency.json`):

| Mode | Runs | Schema pass rate | p50 latency |
|---|---:|---:|---:|
| plan | 3 | 100% | 658 ms |
| troubleshooting | 3 | 100% | 47 ms |
| report | 3 | 100% | 46 ms |

Reproduce with `py scripts/benchmark_generation_latency.py --repeats 3`.
Latency here is the deterministic template path; with a real provider it is
dominated by the model (a `gpt-5` plan generation takes 60-120 s).

Other benchmark scripts:

- `backend/scripts/benchmark_retrieval_backends.py` compares `sql_json`, Chroma, and pgvector when a pgvector database is configured.
- `backend/scripts/eval_authorized_rag.py` evaluates retrieval against an authorized private corpus.

Known limitations:

- The public corpus is synthetic and small; re-measure against your own corpus before quoting any retrieval number.
- The local lexical retriever is not a replacement for production embeddings or reranking.
- The generation benchmark above uses MockProvider, so it measures schema shape and plumbing, not model quality.
- Physics results are deterministic and unit-tested, but a stable cavity on paper is not a guarantee of lasing: pump-mode overlap, coating losses, and alignment still decide the outcome.

## Quick Start on Windows

**Prerequisites** (install once): [Python 3.11+](https://www.python.org/downloads/) (check "Add python.exe to PATH") and [Node.js 22 LTS](https://nodejs.org/).

```bat
Launch-LaserClaw.bat
```

The first run auto-creates a `.env` config (demo mode). For the day-to-day Chinese user guide see [docs/GUIDE_V2.md](docs/GUIDE_V2.md).

The launcher installs backend/frontend dependencies and starts:

- Backend API: <http://127.0.0.1:8000>
- Frontend: <http://127.0.0.1:5173>
- Agent workspace: <http://127.0.0.1:5173/agent>
- API docs: <http://127.0.0.1:8000/docs>

## Manual Local Startup

Backend:

```powershell
cd backend
py -m pip install -r requirements.txt
py -m alembic upgrade head
py -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

Frontend:

```powershell
cd frontend
npm install
npm run dev -- --host 127.0.0.1 --port 5173
```

## Docker

The default Compose file is production-oriented: the backend runs without reload, and the frontend is built as static assets served by nginx.

```bash
docker compose up -d --build
```

Services:

- Frontend: <http://localhost:5173>
- Backend API: <http://localhost:8000>
- API docs: <http://localhost:8000/docs>

For bind-mounted development with hot reload:

```bash
docker compose -f docker-compose.dev.yml up -d --build
```

Stop:

```bash
docker compose down
docker compose -f docker-compose.dev.yml down
```

Deployment and release-gate details are documented in [docs/DEPLOYMENT.md](docs/DEPLOYMENT.md). The current acceptance matrix is tracked in [docs/ACCEPTANCE.md](docs/ACCEPTANCE.md).

## Environment Variables

Create `.env` for local provider and runtime configuration. Do not commit real API keys.

```env
AI_PROVIDER=mock
STRICT_PROVIDER=false

OPENAI_API_KEY=
OPENAI_MODEL=gpt-5
OPENAI_BASE_URL=https://api.openai.com/v1

ANTHROPIC_API_KEY=
ANTHROPIC_MODEL=claude-sonnet-4-5

# Chinese providers (OpenAI-compatible). Set AI_PROVIDER to the vendor name and
# fill in the matching key; base URLs have working defaults.
DEEPSEEK_API_KEY=
DEEPSEEK_MODEL=deepseek-chat
QWEN_API_KEY=
QWEN_MODEL=qwen-plus
ZHIPU_API_KEY=
ZHIPU_MODEL=glm-4-plus
MOONSHOT_API_KEY=
MOONSHOT_MODEL=moonshot-v1-8k

DATABASE_URL=sqlite:///./laserclaw.db
UPLOAD_DIR=./uploads
MAX_UPLOAD_SIZE=52428800
AUTO_CREATE_TABLES=true

EMBEDDING_PROVIDER=local
RETRIEVAL_BACKEND=sql_json
VECTOR_STORE_DIR=./vector_store
DOCKER_VECTOR_STORE_DIR=/app/vector_store
PGVECTOR_DIMENSION=384
RERANKER_PROVIDER=none

REQUIRE_AUTH=false
API_KEY=

VITE_API_URL=http://127.0.0.1:8000
```

Provider modes:

- `mock`: deterministic local demo mode (fixed templates; the UI shows a demo-mode banner)
- `deepseek` / `qwen` / `zhipu` / `moonshot`: Chinese vendors (DeepSeek, Qwen/DashScope, Zhipu GLM, Moonshot Kimi) served over the OpenAI-compatible client
- `openai`: OpenAI-compatible Chat Completions provider
- `anthropic`: Anthropic provider

See `.env.example` for the full annotated template.

Use `STRICT_PROVIDER=true` for strict evaluation so missing or unavailable real providers fail clearly instead of falling back to MockProvider.

## Quality Checks

Backend tests:

```powershell
cd backend
py -m pytest tests -q
```

Backend lint:

```powershell
py -m pip install -r requirements-dev.txt
cd ..
py -m ruff check backend
```

Frontend lint and build:

```powershell
cd frontend
npm ci
npm run lint
npm run build
```

One-command local acceptance check:

```powershell
cd backend
py scripts\acceptance_check.py
```

Final release audit after hosted CI and private eval evidence are available:

```powershell
cd backend
py scripts\final_acceptance_audit.py
```

## Benchmarking

Run the reproducible benchmark:

```powershell
py backend\scripts\benchmark_resume_metrics.py --repeats 10 --top-k 5
```

Skip real LLM calls:

```powershell
py backend\scripts\benchmark_resume_metrics.py --repeats 10 --top-k 5 --skip-llm
```

Authorized private-document evals use JSONL files under `docs/evals/private/`, which are ignored by Git:

```powershell
cd backend
py scripts\index_authorized_docs.py
py scripts\eval_authorized_rag.py --dataset ..\docs\evals\private\rag_eval_authorized_holdout.jsonl --top-k 5 --min-positive-hit-rate 0.85 --min-negative-rejection-rate 0.90
py scripts\tune_retrieval_thresholds.py --dataset ..\docs\evals\private\rag_eval_authorized.jsonl --top-k 5
```

## API Surface

Core endpoints:

- `POST /api/cases`
- `GET /api/cases`
- `GET /api/cases/{case_id}`
- `GET /api/cases/{case_id}/bundle`
- `POST /api/cases/{case_id}/attachments`
- `POST /api/cases/{case_id}/generate-plan`
- `POST /api/cases/{case_id}/generate-troubleshooting`
- `POST /api/cases/{case_id}/generate-report`
- `POST /api/knowledge/sources/upload`
- `GET /api/knowledge/sources`
- `PATCH /api/knowledge/sources/{source_id}/governance`
- `POST /api/knowledge/search`
- `POST /api/agent/chat`
- `POST /api/agent/tasks`
- `GET /api/agent/tasks/{task_id}`
- `POST /api/collaboration/users`
- `POST /api/collaboration/groups`
- `POST /api/collaboration/projects`
- `POST /api/versioning/prompts`
- `POST /api/versioning/workflows`
- `POST /api/evals/rag`
- `POST /api/evals/rag/private-dataset`
- `POST /api/cases/{case_id}/modules`
- `POST /api/cases/modules/{module_id}/run`
- `GET /api/cases/{case_id}/components`
- `GET /api/cases/{case_id}/components/procurement.csv`
- `POST /api/inventory/import`
- `GET /api/inventory/items`
- `GET /api/inventory/sources`
- `DELETE /api/inventory/items`
- `POST /api/inventory/match`
- `POST /api/inventory/items/{item_id}/borrow`
- `POST /api/inventory/loans/{loan_id}/return`
- `GET /api/inventory/loans`
- `PATCH /api/inventory/items/{item_id}/condition`

## Project Structure

```text
LaserClaw/
|-- backend/
|   |-- app/
|   |   |-- agent/          # context, routing, planner, orchestrator, tools
|   |   |-- api/            # FastAPI routes
|   |   |-- auth/           # API-key auth, roles, and project-level ACL
|   |   |-- evals/          # JSONL dataset loading and retrieval metrics
|   |   |-- inventory/      # workbook parsing, import, parameter-level evaluator
|   |   |-- knowledge/      # ingestion, chunking, embeddings, retrieval
|   |   |-- models/         # SQLAlchemy models
|   |   |-- observability/  # audit and usage accounting
|   |   |-- physics/        # deterministic kernel: ABCD/Gaussian, TMM, phase matching,
|   |   |                   #   cavity design search, power-curve fits (pure numpy)
|   |   |-- providers/      # Mock, OpenAI-compatible (OpenAI/DeepSeek/Qwen/Zhipu/Moonshot), Anthropic
|   |   `-- schemas/
|   |-- alembic/
|   |-- scripts/
|   |-- tests/
|   |-- requirements.txt
|   `-- requirements-dev.txt
|-- frontend/
|   |-- src/
|   |   |-- api/
|   |   |-- components/
|   |   |-- pages/
|   |   |-- LanguageContext.jsx
|   |   `-- i18n.js
|   |-- Dockerfile
|   |-- Dockerfile.dev
|   `-- package.json
|-- docs/
|-- docker-compose.yml
|-- docker-compose.dev.yml
|-- pyproject.toml
|-- Launch-LaserClaw.bat
|-- README.md
`-- READMEcn.md
```

## Current Limitations

- API-key authentication is suitable for local and small trusted deployments; shared production deployments should integrate a stronger identity provider and server-issued user context.
- pgvector and Chroma paths are implemented, but production-scale claims require running the documented integration checks with the target deployment configuration.
- Cross-encoder reranking is available but disabled by default because it adds latency and model dependencies.
- Benchmarks use synthetic evaluation documents unless replaced with permissioned real lab documents through the private eval workflow.
- Generated content is advisory and must not be treated as authoritative safety or operating instructions.

## License

MIT License. See [LICENSE](LICENSE).
