"""Test configuration."""
import os

# Ignore any developer .env so the suite never picks up real API keys
# or a different provider. Must be set before app.config is imported.
os.environ["LASERCLAW_NO_DOTENV"] = "1"

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from app.config import get_settings
from app.database import Base
from app import models  # noqa: F401 - register models with Base.metadata
from app.main import app
from app.database import get_db


# Use an in-memory database for API tests.
SQLALCHEMY_DATABASE_URL = "sqlite://"

engine = create_engine(
    SQLALCHEMY_DATABASE_URL,
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


@pytest.fixture(autouse=True)
def use_mock_ai_provider(monkeypatch):
    """Keep API tests deterministic even when the app container uses OpenAI."""
    monkeypatch.setenv("AI_PROVIDER", "mock")
    # Literature search must never hit the network in tests: the mock source
    # returns canned records through the same service path.
    monkeypatch.setenv("LITERATURE_PROVIDERS", "mock")
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    if not os.environ.get("RUN_PGVECTOR_TESTS"):
        monkeypatch.setenv("EMBEDDING_PROVIDER", "local")
        monkeypatch.setenv("RETRIEVAL_BACKEND", "sql_json")
        monkeypatch.setenv("RERANKER_PROVIDER", "none")
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


@pytest.fixture
def db():
    """Create a test database session."""
    Base.metadata.create_all(bind=engine)
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()
        Base.metadata.drop_all(bind=engine)


@pytest.fixture
def client(db):
    """Create a test client."""
    from fastapi.testclient import TestClient

    def override_get_db():
        try:
            yield db
        finally:
            pass

    app.dependency_overrides[get_db] = override_get_db
    client = TestClient(app)
    yield client
    app.dependency_overrides.clear()
