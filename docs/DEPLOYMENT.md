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
- Launcher (`Launch-LaserClaw.bat`) runs: all data lives OUTSIDE the code tree in
  `%USERPROFILE%\LaserClaw-Data` (`laserclaw.db`, `uploads\`, `vector_store\`).
  On first start after upgrading from a pre-2.1 layout, the backend copies the
  legacy in-tree data there automatically (`backend/app/data_migration.py`); the
  in-tree originals are left behind as a backup.
- Manual `uvicorn` runs and Docker keep their configured paths (`backend/laserclaw.db`,
  `/app/uploads`, `VECTOR_STORE_DIR`).
- Private eval datasets: `docs/evals/private`, ignored by Git except `.gitkeep`.
- Authorized lab documents: `uploads/authorized_lab_docs` under the active upload dir, ignored by Git.

## 更新方法（写给实验室同学）

1. 双击代码文件夹里的 **`Update-LaserClaw.bat`**。它会自动:关闭正在运行的
   LaserClaw → 从 GitHub 拉取最新代码 → 重新启动。
2. 如果这台电脑没装 Git(更新器会用中文提示),就找维护者要一份新版压缩包,
   解压到一个**新文件夹**,双击其中的 `Launch-LaserClaw.bat` 即可。
3. 实验数据(元件库、案例、借还记录、附件)保存在 `%USERPROFILE%\LaserClaw-Data`,
   **不在代码文件夹里**——无论哪种更新方式都不会丢数据。
4. 更新后如果页面顶部出现红色横幅"后端程序是旧版本",按横幅提示关闭两个黑色
   窗口再重新双击 `Launch-LaserClaw.bat`(启动器也会自动尝试接管旧进程)。

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
