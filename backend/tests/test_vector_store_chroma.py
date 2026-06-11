from app.config import get_settings
from app.knowledge.ingestion import create_global_file_source
from app.knowledge.retrieval import search_knowledge
from app.knowledge.vector_store import _validate_pgvector_dimension

import pytest


def _fake_dense_embedding(text: str) -> dict:
    lower = text.lower()
    first = 1.0 if any(term in lower for term in ["beam", "alignment", "dump"]) else 0.0
    second = 1.0 if any(term in lower for term in ["coffee", "warranty"]) else 0.0
    return {
        "kind": "dense",
        "provider": "test",
        "model": "test-dense-4",
        "dimensions": 4,
        "values": [first, second, 0.0, 0.0],
    }


def test_chroma_backend_indexes_dense_embeddings(client, db, monkeypatch, tmp_path):
    monkeypatch.setenv("RETRIEVAL_BACKEND", "chroma")
    monkeypatch.setenv("EMBEDDING_PROVIDER", "local")
    monkeypatch.setenv("VECTOR_STORE_DIR", str(tmp_path / "chroma"))
    get_settings.cache_clear()

    # 这里 local 是 sparse，Chroma 不会 index dense vector。
    # 这个测试用来确认 sparse 不会崩。
    path = tmp_path / "sop.txt"
    path.write_text("Beam dumps are required before alignment.", encoding="utf-8")
    source = create_global_file_source(db, title="sop.txt", filepath=str(path), content_type="text/plain")
    db.commit()
    assert source.id

    get_settings.cache_clear()


def test_pgvector_dimension_mismatch_is_explicit(monkeypatch):
    monkeypatch.setenv("PGVECTOR_DIMENSION", "3")
    get_settings.cache_clear()

    with pytest.raises(RuntimeError, match="pgvector embedding dimension mismatch"):
        _validate_pgvector_dimension([0.1, 0.2])

    get_settings.cache_clear()


def test_chroma_backend_retrieves_dense_embeddings(client, db, monkeypatch, tmp_path):
    monkeypatch.setenv("RETRIEVAL_BACKEND", "chroma")
    monkeypatch.setenv("EMBEDDING_PROVIDER", "sentence_transformers")
    monkeypatch.setenv("VECTOR_STORE_DIR", str(tmp_path / "chroma_dense"))
    get_settings.cache_clear()
    monkeypatch.setattr("app.knowledge.ingestion.embed_text", _fake_dense_embedding)
    monkeypatch.setattr("app.knowledge.retrieval.embed_text", _fake_dense_embedding)

    path = tmp_path / "alignment-sop.txt"
    path.write_text("Beam dumps are required before optical alignment.", encoding="utf-8")
    create_global_file_source(db, title="alignment-sop.txt", filepath=str(path), content_type="text/plain")
    db.commit()

    run, results = search_knowledge(db, query="beam dump alignment", top_k=3)

    assert results
    assert results[0].title == "alignment-sop.txt"
    assert run.max_score is not None
    get_settings.cache_clear()
