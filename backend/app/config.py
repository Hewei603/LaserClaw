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
    upload_dir: str = "/app/uploads"
    max_upload_size: int = 10485760  # 10MB

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
