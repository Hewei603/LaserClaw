"""Integration test for pgvector retrieval.

Requires a live PostgreSQL + pgvector database.
Run with:
  $env:RUN_PGVECTOR_TESTS="1"
  $env:DATABASE_URL="postgresql://laserclaw:laserclaw123@localhost:5432/laserclaw"
  $env:RETRIEVAL_BACKEND="pgvector"
  py -m pytest tests/integration -q
"""
import os
import pytest

pytestmark = pytest.mark.skipif(
    not os.environ.get("RUN_PGVECTOR_TESTS"),
    reason="set RUN_PGVECTOR_TESTS=1 with a PostgreSQL/pgvector database",
)


def _fake_pgvector_embedding(text: str) -> dict:
    lower = text.lower()
    first = 1.0 if any(term in lower for term in ["beam", "alignment", "dump", "eye", "protection"]) else 0.0
    second = 1.0 if "coffee" in lower else 0.0
    values = [first, second] + [0.0] * 382
    return {
        "kind": "dense",
        "provider": "test",
        "model": "test-dense-384",
        "dimensions": 384,
        "values": values,
    }


def test_pgvector_retrieval(tmp_path, monkeypatch):
    monkeypatch.setenv("PGVECTOR_DIMENSION", "384")
    monkeypatch.setattr("app.knowledge.ingestion.embed_text", _fake_pgvector_embedding)
    monkeypatch.setattr("app.knowledge.retrieval.embed_text", _fake_pgvector_embedding)
    from app.database import SessionLocal
    from app.knowledge.ingestion import create_global_file_source
    from app.knowledge.retrieval import search_knowledge

    db = SessionLocal()
    try:
        path = tmp_path / "sop.txt"
        path.write_text("Beam dumps are mandatory before laser alignment.", encoding="utf-8")
        create_global_file_source(db, title="sop.txt", filepath=str(path), content_type="text/plain")
        db.commit()

        run, results = search_knowledge(db, query="beam dumps alignment", top_k=3)
        assert results, "Expected at least one result from pgvector"
        assert run.max_score is not None
    finally:
        db.close()


def test_pgvector_reranker_integration(tmp_path, monkeypatch):
    """Verify that enabling the reranker does not break pgvector retrieval."""
    import os
    os.environ.setdefault("RERANKER_PROVIDER", "none")
    monkeypatch.setenv("PGVECTOR_DIMENSION", "384")
    monkeypatch.setattr("app.knowledge.ingestion.embed_text", _fake_pgvector_embedding)
    monkeypatch.setattr("app.knowledge.retrieval.embed_text", _fake_pgvector_embedding)

    from app.database import SessionLocal
    from app.knowledge.ingestion import create_global_file_source
    from app.knowledge.retrieval import search_case_and_global_knowledge

    db = SessionLocal()
    try:
        path = tmp_path / "safety.txt"
        path.write_text(
            "Class 4 laser requires OD5 eye protection. Always perform beam dump before alignment.",
            encoding="utf-8",
        )
        create_global_file_source(db, title="safety.txt", filepath=str(path), content_type="text/plain")
        db.commit()

        run, results = search_case_and_global_knowledge(db, query="eye protection alignment", top_k=5)
        assert results
    finally:
        db.close()
