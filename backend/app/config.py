"""
Application configuration.
"""
import os
from functools import lru_cache
from typing import Optional

from pydantic_settings import BaseSettings
from pathlib import Path

from pydantic import ConfigDict, field_validator

# Look for .env next to the repo root as well as the current working directory,
# so running uvicorn from backend/ still picks up the project-level config.
# Tests set LASERCLAW_NO_DOTENV=1 so a developer's local .env (real API keys,
# a different provider) can never change what the suite exercises.
_REPO_ROOT = Path(__file__).resolve().parents[2]
# Absolute paths only: a relative ".env" would make precedence depend on the
# working directory, which is exactly what this indirection removes.
# Later entries win, so a backend/.env can override the repo-root one.
_ENV_FILES: tuple[str, ...] | None = (
    None
    if os.environ.get("LASERCLAW_NO_DOTENV")
    else (str(_REPO_ROOT / ".env"), str(_REPO_ROOT / "backend" / ".env"))
)

# True inside the application container, where /app IS the project.
# Deliberately POSIX-only: on Windows "/app" is a drive-relative path, so
# Path("/app").is_dir() answers "does C:\\app exist" — and C:\\app is created by
# the very misconfiguration this guard exists to catch, which would make the
# check disable itself after the first stray upload.
_IN_CONTAINER = os.name != "nt" and (Path("/app").is_dir() or Path("/.dockerenv").exists())


def _resolve_data_path(value: str) -> str:
    """Pin a data directory to the repo, not to whatever the CWD happens to be.

    Two failure modes this removes, both of which are silent:

    * A relative path such as ``./backend/vector_store`` resolves differently
      depending on whether uvicorn was started from the repo root or from
      ``backend/``. The launcher uses ``backend/``, so the RAG index written by
      an ingestion run from the repo root would simply be invisible — retrieval
      returns nothing and nothing errors.
    * A container path such as ``/app/uploads`` (which every ``.env`` copied
      from the compose file carries) is *absolute*, so on a local Windows run it
      lands in ``C:\\app\\uploads`` — outside the project, silently.
    """
    text = str(value).strip()
    if not text:
        return text
    path = Path(text)
    if not _IN_CONTAINER:
        parts = path.as_posix().lstrip("/").split("/")
        if path.as_posix().startswith("/app/") and parts[:1] == ["app"]:
            return str(_REPO_ROOT.joinpath(*parts[1:]))
    if path.is_absolute():
        return str(path)
    return str((_REPO_ROOT / path).resolve())


class Settings(BaseSettings):
    """Settings loaded from environment variables or backend/.env."""

    # Database settings
    database_url: str = "sqlite:///./laserclaw.db"

    # File upload settings
    upload_dir: str = "./uploads"
    max_upload_size: int = 52428800  # 50MB

    # AI provider settings
    ai_provider: str = "mock"  # mock, openai, anthropic, deepseek, qwen, zhipu, moonshot
    openai_api_key: Optional[str] = None
    openai_model: str = "gpt-4o-mini"
    openai_base_url: Optional[str] = None
    # Mainland-China OpenAI-compatible providers (reuse the OpenAI client with
    # each vendor's endpoint; set the matching *_API_KEY to enable).
    deepseek_api_key: Optional[str] = None
    deepseek_model: str = "deepseek-chat"
    deepseek_base_url: str = "https://api.deepseek.com/v1"
    qwen_api_key: Optional[str] = None  # Alibaba DashScope compatible mode
    qwen_model: str = "qwen-plus"
    qwen_base_url: str = "https://dashscope.aliyuncs.com/compatible-mode/v1"
    zhipu_api_key: Optional[str] = None  # Zhipu GLM open platform
    zhipu_model: str = "glm-4-plus"
    zhipu_base_url: str = "https://open.bigmodel.cn/api/paas/v4"
    moonshot_api_key: Optional[str] = None  # Moonshot Kimi
    moonshot_model: str = "moonshot-v1-8k"
    moonshot_base_url: str = "https://api.moonshot.cn/v1"
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

    @field_validator("upload_dir", "vector_store_dir")
    @classmethod
    def _pin_to_repo(cls, value: str) -> str:
        return _resolve_data_path(value)

    @field_validator("database_url")
    @classmethod
    def _pin_sqlite_to_backend(cls, value: str) -> str:
        """A relative sqlite path must not depend on the CWD.

        `sqlite:///./laserclaw.db` resolves to a DIFFERENT database depending on
        where uvicorn/alembic was started — the historical data lives in
        backend/laserclaw.db (launcher and alembic both run from backend/), so
        every start location is normalized to that file. Absolute paths,
        :memory: and non-sqlite URLs pass through untouched.
        """
        prefix = "sqlite:///"
        if not value.startswith(prefix) or _IN_CONTAINER:
            return value
        raw = value[len(prefix):]
        if not raw or raw == ":memory:" or Path(raw).is_absolute():
            return value
        resolved = (_REPO_ROOT / "backend" / raw).resolve()
        return prefix + resolved.as_posix()

    model_config = ConfigDict(env_file=_ENV_FILES, extra="ignore")


@lru_cache()
def get_settings() -> Settings:
    """Return cached application settings."""
    return Settings()
