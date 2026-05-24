# LaserClaw

LaserClaw is a local-first **RAG Agent workspace for laser experiment workflows**. It combines experiment case management, global lab knowledge indexing, case-specific evidence retrieval, structured AI artifact generation, persistent Agent traces, and collaboration-oriented governance.

<img width="2534" height="1343" alt="image" src="https://github.com/user-attachments/assets/b8ebb7f4-f980-4671-8722-2ef0913f7f70" />


> Safety note: LaserClaw does not control lasers, power supplies, translation stages, interlocks, optical tables, detectors, or any other lab hardware. Generated content is advisory draft material and must be reviewed by qualified personnel.

## What It Solves

| Problem | LaserClaw approach |
|---|---|
| Lab knowledge is scattered across manuals, SOPs, notes, and case files | Two-tier RAG over global lab documents and case-specific documents |
| AI answers are hard to audit | Stored retrieval runs, citations, generated artifacts, Agent steps, and tool calls |
| Troubleshooting and reporting are repetitive | Structured generation for plans, troubleshooting, reports, and ReZonator drafts |
| Research groups need long-term collaboration | Projects, users, groups, permissions, knowledge governance, versioned prompts/workflows, and case bundles |

## Core Features

- **Case-aware Agent chat**: persistent chat sessions with recent conversation history, linked case data, retrieved knowledge, citations, and retrieval confidence.
- **Two-tier RAG**: global lab documents are treated as lab-wide authority; case-specific attachments and generated artifacts provide local experimental context.
- **Global knowledge base**: upload shared PDFs, TXT, Markdown, CSV, JSON, TSV, or log files for all cases.
- **Case schema v2**: project ownership, status, visibility, tags, measurements, safety notes, conclusions, owner, and schema version.
- **Knowledge governance**: source status (`draft`, `approved`, `deprecated`, `archived`), version, owner, reviewer, review time, and reindexing.
- **Tool-calling Agent workflow**: routes user intent to chat, plan, troubleshooting, report, or ReZonator draft; persists tasks, steps, and tool calls.
- **Structured AI artifacts**: saves plan, troubleshooting, report, image analysis, and resonator outputs as versioned generated content.
- **Prompt/workflow versioning**: manage active prompt and workflow versions for reproducible AI runs.
- **Case bundle export**: export a complete case archive with manifest, attachments, generated content, and knowledge metadata.
- **RAG evals and benchmarks**: reproducible scripts and API for retrieval accuracy, latency, indexing throughput, and LLM JSON reliability.
- **Provider support**: MockProvider, OpenAI-compatible Chat Completions, and Anthropic.
- **Bilingual UI**: English / Chinese frontend language switching.

## Architecture

```text
React + Vite frontend
  -> FastAPI backend
      -> Case / attachment / knowledge / generation / agent / collaboration APIs
      -> SQLAlchemy models
      -> SQLite locally or PostgreSQL in Docker
      -> File uploads and global knowledge documents
      -> RAG ingestion, chunking, embeddings, retrieval, citations
      -> OpenAI / Anthropic / Mock provider
      -> Audit logs, usage tracking, Agent traces, generated artifacts
```

## RAG Workflow

```text
Global PDF / case attachment / generated artifact
  -> text extraction
  -> chunking
  -> embedding
  -> KnowledgeSource + KnowledgeChunk
  -> query-time retrieval
  -> RetrievalRun + RetrievalResult
  -> citation-ready context for chat or artifact generation
```

LaserClaw uses two retrieval tiers:

1. **Global lab knowledge**: safety manuals, SOPs, optical component catalogs, and lab-wide operating rules. These are searched for every case and take precedence when they conflict with case-local data.
2. **Case knowledge**: case data, attachments, image analysis, prior reports, and generated artifacts linked to the current case.

<img width="2533" height="1339" alt="aaf64e0dd186049c62032c55c618898b" src="https://github.com/user-attachments/assets/ffc09e0d-93a4-4259-a07b-c943fbbf4cf9" />

## Agent Workflow

```text
User message
  -> create/find chat session
  -> save user message
  -> route intent
  -> build context:
       current message
       recent chat history
       linked case payload
       global RAG results
       case RAG results
       citations and retrieval confidence
  -> chat response or saved Agent task
  -> save assistant message / task / artifact / citations
```

## Tool Routing

The app supports five intent classes:

| User intent | Tool / mode |
|---|---|
| General chat or QA | `chat` |
| Generate an experiment plan | `generate_plan` |
| Generate troubleshooting guidance | `generate_troubleshooting` |
| Generate an experiment report | `generate_report` |
| Generate a ReZonator / resonator simulation draft | `generate_resonator_draft` |

The chat API can auto-route generation requests, and direct task creation is also available through `POST /api/agent/tasks`.

For ordinary chat, the backend sends a structured context to the provider. For generation requests, it creates an `AgentTask`, builds steps, calls tools, retrieves evidence, generates an artifact, saves it to the case, and stores the full trace.

## RAG and Knowledge Sources

The current RAG stack is deterministic and local. It does not require a vector database:

- tokenization: ASCII terms + Chinese character, bigram, and trigram tokens
- synonym expansion for common safety and optics terms
- section-aware chunking for headings such as `[SAF-PPE]`, `[SAF-SOP]`, `[OPT-MIRROR]`
- section metadata persisted on chunks
- lightweight domain boost for safety-related vs optics-related queries

Current synthetic evaluation documents:

- `synthetic_optical_components_catalog.pdf`: indexed as a PDF global source
- `lab_safety_manual.txt`: indexed as a TXT global source

These are **synthetic evaluation documents**. They are not real laboratory policies, operating procedures, equipment procurement data, or safety training material.

<img width="2555" height="1332" alt="image" src="https://github.com/user-attachments/assets/5f01420a-a81c-4e97-a48c-0d7a22e72dd8" />

## Latest Local Benchmark

The old MockProvider / demo knowledge benchmark is deprecated. The current benchmark was run with OpenAIProvider configuration and synthetic evaluation documents.

| Item | Value |
|---|---|
| Provider | OpenAIProvider |
| Model configured | `gpt-5` |
| Base URL configured | `https://openrouter.ai/api/v1` |
| RAG retrieval queries | 50 |
| RAG answer-generation sample | 30 in the prior full eval |
| Tool routing instructions | 80 |
| Structured artifact generations | 20 |
| End-to-end Agent tasks | 10 |
| Backend tests | 120 passed |

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

RAG optimization improved Top-3 retrieval from 52.27% to 97.73% on the same 50-query synthetic benchmark. A 10-sample RAG answer retest was attempted after the retrieval optimization, but OpenRouter returned `403: This model is not available in your region` for the configured `gpt-5`, so answer-generation retest results are not used as model-quality evidence.

Known benchmark limitations:

- The safety manual is currently indexed as TXT, not as a PDF source.
- Evaluation is based on synthetic documents, not real laboratory data.
- Negative query rejection dropped from 100.00% to 83.33% after stronger recall; score thresholds and abstention logic are still needed.
- Token usage and cost are not exposed by the current provider wrapper.
- The local lexical retriever is not a replacement for production embeddings or reranking.

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

## Docker Compose

```bash
docker compose up -d --build
```

Services:

- Frontend: <http://localhost:5173>
- Backend API: <http://localhost:8000>
- API docs: <http://localhost:8000/docs>

Stop:

```bash
docker compose down
```

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

REQUIRE_AUTH=false
API_KEY=

VITE_API_URL=http://127.0.0.1:8000
```

Provider modes:

- `mock`: deterministic local demo mode
- `openai`: OpenAI-compatible Chat Completions provider
- `anthropic`: Anthropic provider

Use `STRICT_PROVIDER=true` for strict evaluation so missing or unavailable real providers fail clearly instead of falling back to MockProvider.

## Benchmarking

Run the reproducible benchmark:

```powershell
py backend\scripts\benchmark_resume_metrics.py --repeats 10 --top-k 5
```

Skip real LLM calls:

```powershell
py backend\scripts\benchmark_resume_metrics.py --repeats 10 --top-k 5 --skip-llm
```

Reports are generated locally and are not tracked in Git:

```text
docs/benchmarks/
```

## Tests

```powershell
cd backend
py -m pytest tests -q
```

Current local result:

```text
127 passed
```

Frontend build:

```powershell
cd frontend
npm run build
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

## Important Tables

- `experiment_cases`
- `attachments`
- `knowledge_sources`
- `knowledge_chunks`
- `retrieval_runs`
- `retrieval_results`
- `agent_chat_sessions`
- `agent_chat_messages`
- `agent_tasks`
- `agent_steps`
- `agent_tool_calls`
- `generated_contents`
- `organizations`
- `users`
- `groups`
- `projects`
- `prompt_versions`
- `workflow_versions`
- `rag_eval_runs`
- `audit_logs`

## Project Structure

```text
LaserClaw/
|-- backend/
|   |-- app/
|   |   |-- agent/          # context, routing, planner, orchestrator, tools
|   |   |-- api/            # FastAPI routes
|   |   |-- auth/           # API-key auth and coarse roles
|   |   |-- knowledge/      # ingestion, chunking, embeddings, retrieval
|   |   |-- models/         # SQLAlchemy models
|   |   |-- observability/  # audit and usage accounting
|   |   |-- providers/      # Mock, OpenAI, Anthropic
|   |   `-- schemas/
|   |-- alembic/
|   |-- scripts/
|   |-- tests/
|   `-- requirements.txt
|-- frontend/
|   |-- src/
|   |   |-- api/
|   |   |-- pages/
|   |   |-- LanguageContext.jsx
|   |   `-- i18n.js
|   `-- package.json
|-- docs/
|-- Launch-LaserClaw.bat
|-- docker-compose.yml
|-- README.md
`-- READMEcn.md
```

## Current Limitations

- Project/user/group models exist, but fine-grained endpoint authorization still needs hardening.
- Large-corpus retrieval should use a vector backend before claiming production-scale latency.
- Long chat sessions use a recent-message window; automatic long-term memory summarization is not implemented yet.
- Benchmarks use synthetic evaluation documents unless replaced with permissioned real lab documents.
- Generated content is advisory and must not be treated as authoritative safety or operating instructions.

## License

MIT License. See [LICENSE](LICENSE).
