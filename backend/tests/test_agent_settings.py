"""Model configuration must reach real provider calls and survive reloads."""
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from app.agent_settings import PROVIDERS
from app.config import get_settings
from app.providers import get_ai_provider

URL = "/api/settings/agent"


@pytest.fixture(autouse=True)
def isolated_provider_clients(monkeypatch):
    import openai

    calls = []

    class FakeOpenAI:
        def __init__(self, **kwargs):
            self.kwargs = kwargs
            self.chat = SimpleNamespace(completions=SimpleNamespace(create=self.create))

        def create(self, **kwargs):
            calls.append({**self.kwargs, **kwargs})
            return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(
                content='{"title": "Configured provider was called"}',
            ))])

    monkeypatch.setattr(openai, "OpenAI", FakeOpenAI)
    monkeypatch.setattr("app.providers.anthropic.Anthropic", lambda **kwargs: SimpleNamespace(kwargs=kwargs))
    monkeypatch.setattr("app.providers.codex_exec.codex_status", lambda **kwargs: {
        "available": True, "logged_in": True, "ready": True, "auth_method": "chatgpt",
        "version": "test-cli", "executable": "codex", "message": "ready",
    })
    for provider in PROVIDERS:
        monkeypatch.delenv(f"{provider.upper()}_API_KEY", raising=False)
    get_settings.cache_clear()
    return calls


def test_settings_read_existing_env_without_revealing_key(client, monkeypatch):
    monkeypatch.setenv("AI_PROVIDER", "openai")
    monkeypatch.setenv("OPENAI_API_KEY", "secret-env-value")
    monkeypatch.setenv("OPENAI_MODEL", "my-deployment")
    monkeypatch.setenv("OPENAI_BASE_URL", "https://custom.example/v1")
    get_settings.cache_clear()
    response = client.get(URL)
    assert response.status_code == 200
    assert "secret-env-value" not in response.text
    data = response.json()
    assert data["provider"] == "openai"
    option = next(item for item in data["providers"] if item["id"] == "openai")
    assert option["api_key_configured"] is True
    assert option["model"] == "my-deployment"
    assert option["base_url"] == "https://custom.example/v1"


@pytest.mark.parametrize("provider", [name for name in PROVIDERS if name not in {"mock", "codex_exec"}])
def test_save_reaches_factory_and_survives_reload(client, provider):
    response = client.put(URL, json={"provider": provider, "model": "custom-model", "api_key": "secret-saved-value"})
    assert response.status_code == 200, response.text
    assert "secret-saved-value" not in response.text
    assert response.json()["status"]["effective_provider"] == provider
    get_settings.cache_clear()  # fresh settings load, as on backend restart
    instance = get_ai_provider()
    assert instance.api_key == "secret-saved-value"
    assert instance.model == "custom-model"
    assert "secret-saved-value" not in client.get(URL).text


def test_new_config_used_by_next_generation_request(client, isolated_provider_clients):
    response = client.put(URL, json={
        "provider": "openai", "model": "custom-deployment", "api_key": "work-key",
        "base_url": "https://custom.example/v1/",
    })
    assert response.status_code == 200
    cid = client.post("/api/cases", json={"title": "Settings", "goal": "test", "cavity_type": "linear"}).json()["id"]
    result = client.post(f"/api/cases/{cid}/generate-report", json={"use_rag": False})
    assert result.status_code == 200, result.text
    assert result.json()["content"]["title"] == "Configured provider was called"
    call = isolated_provider_clients[-1]
    assert (call["api_key"], call["model"], call["base_url"]) == (
        "work-key", "custom-deployment", "https://custom.example/v1",
    )
    assert client.get("/health").json()["provider"]["is_mock"] is False


def test_switching_providers_and_blank_key_preserve_each_profile(client):
    for provider in ("openai", "deepseek"):
        assert client.put(URL, json={
            "provider": provider, "model": f"{provider}-deployment", "api_key": f"{provider}-key",
        }).status_code == 200
    assert client.put(URL, json={"provider": "mock"}).status_code == 200
    assert client.get("/health").json()["provider"]["is_mock"] is True
    assert client.put(URL, json={"provider": "openai", "model": "updated-model", "api_key": "  "}).status_code == 200
    settings = get_settings()
    assert settings.openai_api_key == "openai-key"
    assert settings.deepseek_api_key == "deepseek-key"
    assert settings.deepseek_model == "deepseek-deployment"
    assert settings.openai_model == "updated-model"
    # A key replacement takes effect immediately too.
    client.put(URL, json={"provider": "openai", "model": "updated-model", "api_key": "replacement-key"})
    assert get_ai_provider().api_key == "replacement-key"


@pytest.mark.parametrize("patch", [
    {"model": " "}, {"api_key": ""}, {"api_key": "has spaces"},
    {"base_url": "not-a-url"}, {"base_url": "https://example.test:wrong/v1"},
    {"provider": "unknown"},
])
def test_invalid_update_keeps_previous_configuration(client, patch):
    client.put(URL, json={"provider": "mock"})
    before = Path(get_settings().agent_settings_file).read_bytes()
    payload = {"provider": "openai", "model": "my-model", "api_key": "test-key", **patch}
    response = client.put(URL, json=payload)
    assert response.status_code == 422
    assert get_settings().ai_provider == "mock"
    assert Path(get_settings().agent_settings_file).read_bytes() == before


def test_failed_disk_write_preserves_previous_settings(client, monkeypatch):
    client.put(URL, json={"provider": "openai", "model": "original-model", "api_key": "original-key"})
    path = Path(get_settings().agent_settings_file)
    before = path.read_bytes()

    def fail_replace(*args):
        raise PermissionError("synthetic write failure")

    monkeypatch.setattr("app.agent_settings.os.replace", fail_replace)
    response = client.put(URL, json={"provider": "openai", "model": "new-model", "api_key": "new-key"})
    assert response.status_code == 500
    assert path.read_bytes() == before
    assert get_ai_provider().model == "original-model"
    assert not list(path.parent.glob(".agent-settings-*.tmp"))


def test_settings_endpoint_uses_existing_auth_rules(client, monkeypatch):
    monkeypatch.setenv("REQUIRE_AUTH", "true")
    monkeypatch.setenv("API_KEY", "application-key")
    get_settings.cache_clear()
    assert client.get(URL).status_code == 401
    assert client.put(URL, json={"provider": "mock"}).status_code == 401
    assert client.get(URL, headers={"X-LaserClaw-API-Key": "application-key"}).status_code == 403


def test_only_model_overrides_persist_and_environment_defaults_stay_intact(client, monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "env-key")
    monkeypatch.setenv("OPENAI_BASE_URL", "https://existing.example/v1")
    get_settings.cache_clear()
    assert client.put(URL, json={"provider": "openai", "model": "replacement"}).status_code == 200
    settings = get_settings()
    assert settings.openai_api_key == "env-key"
    assert settings.openai_base_url == "https://existing.example/v1"
    stored = json.loads(Path(settings.agent_settings_file).read_text())
    assert stored == {"ai_provider": "openai", "openai_model": "replacement"}


@pytest.mark.parametrize("failure, expected_status, detail", [
    (RuntimeError("API key 无效或无权限"), 502, "API key 无效或无权限"),
    (ValueError("unexpected internal failure"), 500, "Internal server error"),
])
def test_chat_errors_remain_readable_in_browser(client, monkeypatch, failure, expected_status, detail):
    class BrokenProvider:
        async def generate_chat_response(self, context):
            raise failure

    monkeypatch.setattr("app.api.agent.get_ai_provider", BrokenProvider)
    response = client.post("/api/agent/chat", json={"message": "hello", "mode": "chat"},
                           headers={"Origin": "http://localhost:5173"})
    assert response.status_code == expected_status
    assert response.json()["detail"] == detail
    assert response.headers["access-control-allow-origin"] == "http://localhost:5173"
    assert "x-request-id" in response.headers or expected_status == 500
