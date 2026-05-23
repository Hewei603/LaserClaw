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

    if provider_name != "mock":
        logger.warning("Unknown AI_PROVIDER=%s; falling back to MockProvider", provider_name)
    return MockProvider()
