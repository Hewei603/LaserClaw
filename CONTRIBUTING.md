# Contributing to LaserClaw

LaserClaw is a local-first RAG Agent workspace for laser experiment knowledge workflows. Contributions should preserve the core guarantees: auditable retrieval, citation-ready outputs, project-level access control, and deterministic local testing.

## Development Setup

Backend:

```powershell
cd backend
py -m pip install -r requirements.txt
py -m pytest tests -q
```

Frontend:

```powershell
cd frontend
npm ci
npm run build
```

Docker:

```powershell
docker compose up --build
```

## Pull Request Checklist

- Add or update tests for changed backend behavior.
- Run `py -m pytest tests -q` from `backend`.
- Run `npm run build` from `frontend` when frontend files change.
- Keep RAG changes auditable: preserve `RetrievalRun`, `RetrievalResult`, citations, and confidence/no-answer behavior.
- Keep authorization checks before retrieval whenever case/project data is involved.
- Do not commit real lab documents, API keys, model caches, uploaded files, or private eval datasets.

## RAG and ACL Expectations

- SQL metadata remains authoritative even when Chroma or pgvector is enabled.
- Global knowledge may be retrieved for all authorized users unless archived.
- Case-specific chunks must be filtered by project/case access before retrieval results are returned.
- Rerankers must operate on a bounded candidate set, not the full corpus.

## Reporting Bugs

Include the backend mode, database backend, retrieval backend, embedding provider, and the smallest reproducible case or document sample. Use synthetic or redacted data only.
