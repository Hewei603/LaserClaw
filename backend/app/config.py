"""
Application configuration.
"""
from functools import lru_cache
from typing import Optional

from pydantic_settings import BaseSettings
from pydantic import ConfigDict


class Settings(BaseSettings):
    """Settings loaded from environment variables or backend/.env."""

    # Database settings
    database_url: str = "sqlite:///./laserclaw.db"

    # File upload settings
    upload_dir: str = "./uploads"
    max_upload_size: int = 52428800  # 50MB

    # AI provider settings
    ai_provider: str = "mock"  # mock, openai, anthropic
    openai_api_key: Optional[str] = None
    openai_model: str = "gpt-4o-mini"
    openai_base_url: Optional[str] = None
    anthropic_api_key: Optional[str] = None
    anthropic_model: str = "claude-sonnet-4-5"
    anthropic_max_tokens: int = 2048
    anthropic_temperature: float = 0.2
    environment: str = "local"
    strict_provider: bool = False
    auto_create_tables: bool = True
    require_auth: bool = False
    api_key: Optional[str] = None

    # RAG and embedding settings
    embedding_provider: str = "local"  # local, openai, sentence_transformers
    embedding_model: str = "text-embedding-3-small"
    retrieval_backend: str = "sql_json"  # sql_json; optional vector DB adapters can share this interface
    vector_store_dir: str = "/app/vector_store"
    retrieval_vector_weight: float = 0.72
    retrieval_lexical_weight: float = 0.28
    retrieval_min_score: float = 0.08
    retrieval_low_confidence_score: float = 0.14
    retrieval_min_results: int = 1
    retrieval_answer_margin_min: float = 0.03
    retrieval_negative_policy: str = "score_and_margin"
    pgvector_table: str = "knowledge_chunk_vectors"
    pgvector_dimension: int = 384

    # Reranker settings
    reranker_provider: str = "none"  # none, sentence_transformers, cohere
    reranker_model: str = "cross-encoder/ms-marco-MiniLM-L-6-v2"
    reranker_top_k: int = 20
    reranker_weight: float = 0.65

    # CORS settings
    cors_origins: list[str] = [
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "http://localhost:3000",
        "http://127.0.0.1:3000",
    ]

    model_config = ConfigDict(env_file=".env", extra="ignore")


@lru_cache()
def get_settings() -> Settings:
    """Return cached application settings."""
    return Settings()
