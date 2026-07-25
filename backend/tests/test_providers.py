"""
AI provider tests.
"""
import sys
import types

import pytest

from app.config import get_settings
from app.providers import get_ai_provider
from app.providers.anthropic import AnthropicProvider
from app.providers.mock import MockProvider
from app.providers.openai import OpenAIProvider


@pytest.fixture(autouse=True)
def clear_settings_cache():
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


@pytest.mark.asyncio
async def test_mock_provider_generate_plan():
    """Mock provider can generate an experiment plan."""
    provider = MockProvider()
    case_data = {
        "cavity_type": "linear",
        "goal": "test goal",
    }

    result = await provider.generate_plan(case_data)

    assert "disclaimer" in result
    assert "steps" in result
    assert len(result["steps"]) > 0


@pytest.mark.asyncio
async def test_mock_provider_generate_rezonator():
    """Mock provider can generate a ReZonator schema draft."""
    provider = MockProvider()
    case_data = {
        "cavity_type": "ring",
        "parameters": {"wavelength": "800nm"},
    }

    result = await provider.generate_rezonator_schema(case_data)

    assert "disclaimer" in result
    assert "cavity_type" in result
    assert "elements" in result


@pytest.mark.asyncio
async def test_mock_provider_generate_troubleshooting():
    """Mock provider can generate troubleshooting advice."""
    provider = MockProvider()
    symptoms = ["no output", "thermal issue"]
    case_data = {"cavity_type": "linear"}

    result = await provider.generate_troubleshooting(symptoms, case_data)

    assert "disclaimer" in result
    assert "suggestions" in result


@pytest.mark.asyncio
async def test_mock_provider_generate_report():
    """Mock provider can generate a report draft."""
    provider = MockProvider()
    case_data = {
        "title": "test case",
        "cavity_type": "linear",
        "goal": "test goal",
    }

    result = await provider.generate_report(case_data)

    assert "disclaimer" in result
    assert "title" in result
    assert "sections" in result


def test_get_ai_provider_defaults_to_mock(monkeypatch):
    """MockProvider remains the default demo provider."""
    monkeypatch.delenv("AI_PROVIDER", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)

    provider = get_ai_provider()

    assert isinstance(provider, MockProvider)


def test_provider_factory_returns_mock_by_default(monkeypatch):
    """AI_PROVIDER defaults to MockProvider."""
    monkeypatch.delenv("AI_PROVIDER", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)

    provider = get_ai_provider()

    assert isinstance(provider, MockProvider)


def test_get_ai_provider_falls_back_to_mock_without_openai_key(monkeypatch):
    """OpenAI mode without an API key should not break demo mode."""
    monkeypatch.setenv("AI_PROVIDER", "openai")
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)

    provider = get_ai_provider()

    assert isinstance(provider, MockProvider)


def test_get_ai_provider_returns_openai_provider_when_configured(monkeypatch):
    """OpenAI mode returns OpenAIProvider when the SDK and API key are available."""
    class FakeOpenAI:
        def __init__(self, **kwargs):
            self.kwargs = kwargs

    fake_openai_module = types.SimpleNamespace(OpenAI=FakeOpenAI)
    monkeypatch.setitem(sys.modules, "openai", fake_openai_module)
    monkeypatch.setenv("AI_PROVIDER", "openai")
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    monkeypatch.setenv("OPENAI_MODEL", "test-model")
    monkeypatch.setenv("OPENAI_BASE_URL", "https://example.test/v1")

    provider = get_ai_provider()

    assert isinstance(provider, OpenAIProvider)
    assert provider.model == "test-model"
    assert provider.client.kwargs == {
        "api_key": "test-key",
        "base_url": "https://example.test/v1",
    }


def test_provider_factory_falls_back_to_mock_when_anthropic_key_missing_and_not_strict(monkeypatch):
    """Anthropic mode without a key falls back to mock unless strict mode is enabled."""
    monkeypatch.setenv("AI_PROVIDER", "anthropic")
    monkeypatch.setenv("STRICT_PROVIDER", "false")
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)

    provider = get_ai_provider()

    assert isinstance(provider, MockProvider)


def test_provider_factory_raises_when_anthropic_key_missing_and_strict(monkeypatch):
    """Strict Anthropic mode fails clearly when no API key is configured."""
    monkeypatch.setenv("AI_PROVIDER", "anthropic")
    monkeypatch.setenv("STRICT_PROVIDER", "true")
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)

    with pytest.raises(RuntimeError, match="ANTHROPIC_API_KEY"):
        get_ai_provider()


def test_provider_factory_returns_anthropic_provider_when_configured(monkeypatch):
    """Anthropic mode returns AnthropicProvider when the SDK and API key are available."""
    class FakeAnthropicClient:
        def __init__(self, **kwargs):
            self.kwargs = kwargs

    monkeypatch.setattr("app.providers.anthropic.Anthropic", FakeAnthropicClient)
    monkeypatch.setenv("AI_PROVIDER", "anthropic")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-anthropic-key")
    monkeypatch.setenv("ANTHROPIC_MODEL", "test-claude")
    monkeypatch.setenv("ANTHROPIC_MAX_TOKENS", "1234")
    monkeypatch.setenv("ANTHROPIC_TEMPERATURE", "0.4")

    provider = get_ai_provider()

    assert isinstance(provider, AnthropicProvider)
    assert provider.model == "test-claude"
    assert provider.max_tokens == 1234
    assert provider.temperature == 0.4
    assert provider.client.kwargs == {"api_key": "test-anthropic-key"}


def test_openai_provider_requires_api_key(monkeypatch):
    """OpenAIProvider itself fails clearly when no key is supplied."""
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)

    with pytest.raises(ValueError, match="OPENAI_API_KEY"):
        OpenAIProvider(api_key=None)


def test_anthropic_provider_extracts_json_from_plain_json():
    """AnthropicProvider can parse plain JSON objects."""
    provider = object.__new__(AnthropicProvider)

    result = provider._extract_json('{"title": "Plan", "steps": []}')

    assert result == {"title": "Plan", "steps": []}


def test_anthropic_provider_extracts_json_from_fenced_json():
    """AnthropicProvider strips common fenced JSON blocks before parsing."""
    provider = object.__new__(AnthropicProvider)

    result = provider._extract_json('```json\n{"title": "Plan", "steps": []}\n```')

    assert result == {"title": "Plan", "steps": []}


@pytest.mark.asyncio
async def test_anthropic_provider_rejects_unsupported_image_mime_type_without_api_call():
    """Unsupported image formats return structured JSON without calling Claude."""
    provider = object.__new__(AnthropicProvider)
    provider.model = "test-claude"
    provider.client = None

    result = await provider.analyze_image(b"fake", "image/bmp", {"case": {"title": "test"}})

    assert result["error"] == "unsupported_image_mime_type"
    assert result["model_provider"] == "anthropic"
    assert result["model"] == "test-claude"


def test_cn_provider_deepseek_uses_openai_client(monkeypatch):
    from app.config import get_settings
    from app.providers import get_ai_provider

    monkeypatch.setenv("AI_PROVIDER", "deepseek")
    monkeypatch.setenv("DEEPSEEK_API_KEY", "test-ds-key")
    get_settings.cache_clear()
    provider = get_ai_provider()
    get_settings.cache_clear()
    assert provider.__class__.__name__ == "OpenAIProvider"
    assert provider.model == "deepseek-chat"
    assert "deepseek.com" in provider.base_url


def test_cn_provider_without_key_falls_back_to_mock(monkeypatch):
    from app.config import get_settings
    from app.providers import get_ai_provider

    for name in ("qwen", "zhipu", "moonshot"):
        monkeypatch.setenv("AI_PROVIDER", name)
        monkeypatch.delenv(f"{name.upper()}_API_KEY", raising=False)
        monkeypatch.delenv("STRICT_PROVIDER", raising=False)
        get_settings.cache_clear()
        provider = get_ai_provider()
        assert provider.__class__.__name__ == "MockProvider", name
    get_settings.cache_clear()


def test_cn_provider_qwen_endpoint(monkeypatch):
    from app.config import get_settings
    from app.providers import get_ai_provider

    monkeypatch.setenv("AI_PROVIDER", "qwen")
    monkeypatch.setenv("QWEN_API_KEY", "test-qw-key")
    get_settings.cache_clear()
    provider = get_ai_provider()
    get_settings.cache_clear()
    assert "dashscope.aliyuncs.com" in provider.base_url
    assert provider.model == "qwen-plus"
