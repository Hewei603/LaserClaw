"""AI provider factory."""
import logging

from .base import AIProvider
from .mock import MockProvider
from ..config import get_settings

logger = logging.getLogger(__name__)


def get_ai_provider() -> AIProvider:
    """
    Return the configured AI provider.

    MockProvider remains the safe fallback for demo mode, missing API keys,
    unknown provider names, or an unavailable external SDK.
    """
    settings = get_settings()
    provider_name = settings.ai_provider.lower()

    if provider_name == "openai":
        if not settings.openai_api_key:
            message = "AI_PROVIDER=openai but OPENAI_API_KEY is missing"
            if settings.strict_provider:
                raise RuntimeError(message)
            logger.warning("%s; falling back to MockProvider", message)
            return MockProvider()

        try:
            from .openai import OpenAIProvider

            return OpenAIProvider()
        except (ImportError, RuntimeError, ValueError) as exc:
            if settings.strict_provider:
                raise
            logger.warning("OpenAI provider unavailable (%s); falling back to MockProvider", exc)
            return MockProvider()

    if provider_name == "anthropic":
        if not settings.anthropic_api_key:
            message = "AI_PROVIDER=anthropic but ANTHROPIC_API_KEY is missing"
            if settings.strict_provider:
                raise RuntimeError(message)
            logger.warning("%s; falling back to MockProvider", message)
            return MockProvider()

        try:
            from .anthropic import AnthropicProvider

            return AnthropicProvider()
        except Exception as exc:
            if settings.strict_provider:
                raise
            logger.warning("Anthropic provider unavailable (%s); falling back to MockProvider", exc)
            return MockProvider()

    # Mainland-China OpenAI-compatible providers: reuse the OpenAI client with
    # the vendor's endpoint, key, and default model.
    cn_compatible = {
        "deepseek": (settings.deepseek_api_key, settings.deepseek_model, settings.deepseek_base_url),
        "qwen": (settings.qwen_api_key, settings.qwen_model, settings.qwen_base_url),
        "zhipu": (settings.zhipu_api_key, settings.zhipu_model, settings.zhipu_base_url),
        "moonshot": (settings.moonshot_api_key, settings.moonshot_model, settings.moonshot_base_url),
    }
    if provider_name in cn_compatible:
        api_key, model, base_url = cn_compatible[provider_name]
        if not api_key:
            message = f"AI_PROVIDER={provider_name} but {provider_name.upper()}_API_KEY is missing"
            if settings.strict_provider:
                raise RuntimeError(message)
            logger.warning("%s; falling back to MockProvider", message)
            return MockProvider()
        try:
            from .openai import OpenAIProvider

            return OpenAIProvider(api_key=api_key, model=model, base_url=base_url)
        except Exception as exc:  # match the anthropic branch: always fall back
            if settings.strict_provider:
                raise
            logger.warning("%s provider unavailable (%s); falling back to MockProvider", provider_name, exc)
            return MockProvider()

    if provider_name != "mock":
        # A typo like "deepseak" must not silently demote the app to demo data:
        # strict mode treats it exactly like a missing key.
        message = f"Unknown AI_PROVIDER={provider_name}"
        if settings.strict_provider:
            raise RuntimeError(message + " (check the spelling in .env)")
        logger.warning("%s; falling back to MockProvider", message)
    return MockProvider()


def provider_status() -> dict:
    """Which provider is actually in effect — for /health and the UI banner.

    The configured name and the effective provider can differ (missing key,
    SDK import failure), and that difference is exactly what the user needs
    to see: mock output is indistinguishable from real output by tone alone.
    """
    settings = get_settings()
    try:
        provider = get_ai_provider()
    except Exception as exc:  # strict mode surfaces the misconfiguration
        return {
            "configured_provider": settings.ai_provider,
            "effective_provider": None,
            "is_mock": False,
            "error": str(exc),
        }
    is_mock = isinstance(provider, MockProvider)
    return {
        "configured_provider": settings.ai_provider,
        "effective_provider": "mock" if is_mock else settings.ai_provider.lower(),
        "is_mock": is_mock,
    }
