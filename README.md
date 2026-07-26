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
- **Structured AI artifacts** saved as versioned generated content.
- **Prompt/workflow versioning** for reproducible AI runs.
- **Case bundle export** with manifest, attachments, generated content, and knowledge metadata.
- **Project-level ACL** across cases, knowledge search, attachments, generation, Agent tasks, case modules, and bundle export.
- **RAG evals and benchmarks** for retrieval quality, latency, indexing throughput, and JSON reliability.
- **Retrieval backends** including deterministic `sql_json`, Chroma, pgvector, and optional cross-encoder reranking.
- **Provider support** for MockProvider, OpenAI-compatible Chat Completions, and Anthropic.
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
      -> OpenAI / Anthropic / Mock provider
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

The public benchmark uses synthetic documents so the repository can be tested without private lab data. These documents are not real laboratory policies, equipment data, or safety training material.

| Item | Value |
|---|---|
| Provider used for latest local benchmark | OpenAIProvider |
| Configured model | `gpt-5` via OpenRouter during that run |
| RAG retrieval queries | 50 |
| Tool routing instructions | 80 |
| Structured artifact generations | 20 |
| End-to-end Agent tasks | 10 |
| Backend tests | 161 passed, 2 skipped |
| API auth dependency audit | 70 `/api/*` routes checked, 0 findings |
| Frontend lint/build | Passed |

| Metric | Result |
|---|---:|
| RAG Top-1 hit rate | 95.45% |
| RAG Top-3 hit rate | 97.73% |
| RAG MRR | 0.9678 |
| Citation correctness | 82.00% |
| Tool routing accuracy | 80.00% |
| Schema pass rate | 100.00% |
| End-to-end task success rate | 100.00% |
| Trace completeness | 100.00% |

Additional v1.0 benchmark scripts are available:

- `backend/scripts/benchmark_retrieval_backends.py` compares `sql_json`, Chroma, and pgvector when a pgvector database is configured.
- `backend/scripts/benchmark_generation_latency.py` measures structured generation latency and output shape by task type.
- `backend/scripts/audit_endpoint_acl.py` audits FastAPI routes for principal dependency coverage.

Known benchmark limitations:

- Evaluation is based on synthetic documents unless replaced with authorized private datasets.
- The local lexical retriever is not a replacement for production embeddings or reranking.
- Token usage and cost are not exposed by the current provider wrapper.
- Production retrieval claims should be re-measured against the deployment's target corpus and backend.

## Quick Start on Windows

```bat
Launch-LaserClaw.bat
```

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
OPENAI_MODEL=gpt-4o
OPENAI_BASE_URL=https://api.openai.com/v1

ANTHROPIC_API_KEY=
ANTHROPIC_MODEL=claude-sonnet-4-5

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

- `mock`: deterministic local demo mode
- `openai`: OpenAI-compatible Chat Completions provider
- `anthropic`: Anthropic provider

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
- `POST /api/cases/{case_id}/generate-rezonator`
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

## Project Structure

```text
LaserClaw/
|-- backend/
|   |-- app/
|   |   |-- agent/          # context, routing, planner, orchestrator, tools
|   |   |-- api/            # FastAPI routes
|   |   |-- auth/           # API-key auth, roles, and project-level ACL
|   |   |-- evals/          # JSONL dataset loading and retrieval metrics
|   |   |-- knowledge/      # ingestion, chunking, embeddings, retrieval
|   |   |-- models/         # SQLAlchemy models
|   |   |-- observability/  # audit and usage accounting
|   |   |-- providers/      # Mock, OpenAI, Anthropic
|   |   `-- schemas/
|   |-- alembic/
|   |-- scripts/
|   |-- tests/
|   |-- requirements.txt
|   `-- requirements-dev.txt
|-- frontend/
|   |-- src/
|   |   |-- api/
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
