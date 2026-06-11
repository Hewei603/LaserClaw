# LaserClaw Deployment and Acceptance Guide

This guide defines the operational checks for a production-oriented LaserClaw deployment.

## Local Smoke Test

```powershell
cd backend
py -m pip install -r requirements-dev.txt
cd ..
py -m ruff check backend
cd backend
py -m pytest tests -q
py scripts\audit_endpoint_acl.py --fail-on-findings
py scripts\benchmark_retrieval_backends.py --backends sql_json,chroma --repeats 10 --top-k 5
py scripts\benchmark_generation_latency.py --repeats 3

cd ..\frontend
npm ci
npm run lint
npm run build
```

Acceptance:

- Backend tests pass.
- API auth dependency audit reports zero findings.
- Synthetic retrieval and generation benchmark reports are produced.
- Frontend build completes.
- No real API keys or private documents are required.

## Docker Compose

Docker Desktop or another Docker daemon must be running before this check.
The default Compose file is production-oriented: the backend runs without hot reload, and the frontend is built as static assets served by nginx.
The frontend build stage uses Node 22 because the current Vite version requires Node 20.19+ or 22.12+.
The backend base image installs `requirements.txt`; install `requirements-ml.txt` only for deployments that need local sentence-transformers models.
Compose uses `DOCKER_VECTOR_STORE_DIR` for the container path and defaults it to `/app/vector_store`, so local `VECTOR_STORE_DIR` values do not leak into the container filesystem layout.

```powershell
docker compose up -d --build
docker compose ps
```

Expected services:

- `laserclaw_db`
- `laserclaw_backend`
- `laserclaw_frontend`

Smoke endpoints:

```powershell
curl http://127.0.0.1:8000/health
curl http://127.0.0.1:8000/docs
```

Stop:

```powershell
docker compose down
```

For bind-mounted development with hot reload:

```powershell
docker compose -f docker-compose.dev.yml up -d --build
docker compose -f docker-compose.dev.yml down
```

## Authentication

Local demos may run with:

```env
REQUIRE_AUTH=false
```

Shared or production-like deployments should use:

```env
REQUIRE_AUTH=true
API_KEY=replace-with-a-secret
```

Clients must send:

```text
X-LaserClaw-API-Key: replace-with-a-secret
X-User-Id: <user id>
X-User-Role: user|reviewer|admin
```

Project-level ACL is enforced for cases, knowledge search, attachments, generated content, Agent tasks, case modules, and bundle export.

The built-in API-key mode is suitable for local and small trusted deployments. For shared production deployments, put LaserClaw behind a proper identity provider or reverse proxy that issues trusted user context server-side.

## Data Locations

- Database: SQLite locally or PostgreSQL in Docker.
- Uploads: `backend/uploads` locally or `/app/uploads` in Docker.
- Chroma vector store: `VECTOR_STORE_DIR`.
- Private eval datasets: `docs/evals/private`, ignored by Git except `.gitkeep`.
- Authorized lab documents: `backend/uploads/authorized_lab_docs`, ignored by Git.

## Backup Guidance

For SQLite, back up the `.db` file and `backend/uploads`.

For Docker/PostgreSQL:

```powershell
docker exec laserclaw_db pg_dump -U laserclaw laserclaw > laserclaw-backup.sql
```

Also back up upload and vector-store volumes:

- `backend_uploads`
- `backend_vector_store`

## Release Gate

A release candidate should pass:

```powershell
cd backend
py scripts\acceptance_check.py
py scripts\benchmark_retrieval_backends.py --backends sql_json,chroma --repeats 10 --top-k 5
py scripts\benchmark_generation_latency.py --repeats 3
```

For production retrieval claims, also run the relevant vector backend checks in `docs/RAG_OPERATIONS.md`.
