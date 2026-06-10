# LaserClaw Deployment and Acceptance Guide

This guide defines the operational checks for a production-oriented LaserClaw deployment.

## Local Smoke Test

```powershell
cd backend
py -m pip install -r requirements.txt
py -m pytest tests -q

cd ..\frontend
npm ci
npm run build
```

Acceptance:

- Backend tests pass.
- Frontend build completes.
- No real API keys or private documents are required.

## Docker Compose

Docker Desktop or another Docker daemon must be running before this check.
The frontend image uses Node 22 because the current Vite version requires Node 20.19+ or 22.12+.
The backend base image installs `requirements.txt`; install `requirements-ml.txt` only for deployments that need local sentence-transformers models.

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
```

For production retrieval claims, also run the relevant vector backend checks in `docs/RAG_OPERATIONS.md`.
