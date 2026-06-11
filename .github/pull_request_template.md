## Summary

-

## Risk Areas

- [ ] RAG retrieval, citations, confidence, or no-answer behavior
- [ ] ACL, project visibility, or data isolation
- [ ] Agent tasks, tool calls, or generated artifacts
- [ ] Database models or Alembic migrations
- [ ] Frontend workflow or layout
- [ ] Deployment, Docker, or CI

## Verification

- [ ] `cd backend; py -m pytest tests -q`
- [ ] `cd backend; py -m alembic upgrade head` against an empty temporary database
- [ ] `cd frontend; npm run build`
- [ ] pgvector integration if retrieval backend changed
- [ ] Private/synthetic RAG eval if retrieval ranking changed

## Data Safety

- [ ] No API keys, real lab documents, private eval datasets, uploads, model caches, or generated reports are committed.
- [ ] Any examples use synthetic or explicitly authorized data.
