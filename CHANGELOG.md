# Changelog

## Unreleased

- Fixed the stale-backend deployment gap: the launcher now takes over ports held by old LaserClaw processes, `/health` reports the app version, and the frontend shows a Chinese "restart the launcher" banner on version mismatch (`tests/test_version_handshake.py` pins the three version strings together).
- Moved launcher-run experiment data out of the code tree to `%USERPROFILE%\LaserClaw-Data`, with a one-time automatic copy of legacy in-tree data (`backend/app/data_migration.py`) and a new `Update-LaserClaw.bat` one-click updater.
- Integrated crystal cut-angle matching into the L1 inventory evaluator (`phase_match` requirement: per-material phase-match angle vs labelled cut, three-state with 180°−θ equivalence) and added a "nonlinear crystal (cut angle)" mode to the inventory match form.
- Added a full-BOM export (`/api/cases/{id}/components/bom.csv`, Chinese headers, owned parts included) for the teardown 泵表 deliverable; both component CSVs now carry a UTF-8 BOM so Excel renders Chinese correctly.
- Closed real-workbook geometry parsing gaps (lens focal lengths `F=300mm/f=250 mm/F100` into a new `focal_length_mm` field + migration 0010, `Φ25*5mm` diameter×thickness, `D>18mm` lower bounds); geometry cells that still parse to nothing now downgrade the row to the review queue with a "几何列未解析" note instead of vanishing.
- Replaced the raw-JSON module run config with typed per-module Chinese forms (cavity design / phase match / coating / power curve / stability); the JSON textarea remains as an advanced override.

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
