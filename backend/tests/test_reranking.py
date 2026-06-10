"""Tests for the two-stage reranker module."""
import pytest
from app.knowledge.reranking import rerank_chunks
from app.config import get_settings


class _FakeChunk:
    def __init__(self, text: str) -> None:
        self.text = text


def test_rerank_none_returns_top_k(monkeypatch):
    monkeypatch.setenv("RERANKER_PROVIDER", "none")
    get_settings.cache_clear()

    chunks = [
        (0.9, _FakeChunk("a")),
        (0.7, _FakeChunk("b")),
        (0.5, _FakeChunk("c")),
    ]
    result = rerank_chunks("query", chunks, top_k=2)
    assert len(result) == 2
    assert result[0][1].text == "a"
    assert result[1][1].text == "b"

    get_settings.cache_clear()


def test_rerank_none_empty_list(monkeypatch):
    monkeypatch.setenv("RERANKER_PROVIDER", "none")
    get_settings.cache_clear()

    result = rerank_chunks("anything", [], top_k=5)
    assert result == []
    get_settings.cache_clear()


def test_rerank_none_top_k_larger_than_list(monkeypatch):
    monkeypatch.setenv("RERANKER_PROVIDER", "none")
    get_settings.cache_clear()

    chunks = [(0.5, _FakeChunk("x"))]
    result = rerank_chunks("query", chunks, top_k=10)
    assert len(result) == 1
    get_settings.cache_clear()


def test_rerank_unsupported_provider_raises(monkeypatch):
    monkeypatch.setenv("RERANKER_PROVIDER", "cohere")
    get_settings.cache_clear()

    with pytest.raises(RuntimeError, match="Unsupported reranker provider"):
        rerank_chunks("query", [(0.5, _FakeChunk("x"))], top_k=1)
    get_settings.cache_clear()


def test_sentence_transformers_reranker_reorders_with_fake_model(monkeypatch):
    class FakeCrossEncoder:
        def predict(self, pairs):
            return [0.1 if "weak" in text else 0.9 for _, text in pairs]

    monkeypatch.setenv("RERANKER_PROVIDER", "sentence_transformers")
    monkeypatch.setenv("RERANKER_WEIGHT", "0.9")
    get_settings.cache_clear()
    monkeypatch.setattr("app.knowledge.reranking._load_cross_encoder", lambda model_name: FakeCrossEncoder())

    chunks = [
        (0.9, _FakeChunk("weak candidate")),
        (0.4, _FakeChunk("strong candidate")),
    ]

    result = rerank_chunks("query", chunks, top_k=2)

    assert result[0][1].text == "strong candidate"
    get_settings.cache_clear()
