# Changelog

## Unreleased

- Added an MIT `LICENSE` file for open-source distribution.
- Added a public synthetic RAG eval JSONL example and wired its format check into the local acceptance script.
- Added configurable score/margin abstention settings for ambiguous retrieval results.
- Added strict JSONL eval row validation, private eval path containment checks, and CI backend acceptance extras.
- Added CLI acceptance thresholds for authorized RAG eval holdout runs.
- Added a final acceptance audit script for local, hosted CI, and private eval gates.
- Updated local acceptance evidence to `161 passed, 2 skipped`.
- Added project-level ACL helpers and enforced case access across case, knowledge, attachment, generation, and Agent APIs.
- Added pre-retrieval RAG filtering so case-specific chunks are not returned to unauthorized users.
- Aligned pgvector defaults with the example dense embedding model dimension.
- Added explicit pgvector embedding dimension validation.
- Added CI for backend tests and frontend builds.
- Added contribution, security, and code of conduct documentation.
- Added JSONL RAG eval loading, positive/negative retrieval metrics, private dataset eval endpoint, and threshold tuning scripts.
- Added case module ACL coverage so module files, analysis runs, and component/procurement items follow case permissions.
- Added authorized lab document import workflow, deployment/RAG operations documentation, and Docker health checks.
- Made the pgvector migration dialect-aware so local SQLite Alembic upgrades remain valid while PostgreSQL uses pgvector.
- Added an enterprise acceptance matrix, CI pgvector integration job, Chroma dense retrieval coverage, and enabled-reranker coverage.
- Split optional sentence-transformers dependencies into `requirements-ml.txt` and added a backend `.dockerignore` for lean Docker builds.
- Added issue/PR templates and a local `acceptance_check.py` script.
- Verified Docker Compose startup and live pgvector integration locally.
