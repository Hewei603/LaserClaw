"""
AI提供者工厂
"""
from .base import AIProvider
from .mock import MockProvider
from ..config import get_settings


def get_ai_provider() -> AIProvider:
    """
    获取AI提供者实例

    Returns:
        AI提供者实例
    """
    settings = get_settings()

    if settings.ai_provider == "mock":
        return MockProvider()
    # 未来可以添加其他提供者
    # elif settings.ai_provider == "openai":
    #     return OpenAIProvider()
    # elif settings.ai_provider == "anthropic":
    #     return AnthropicProvider()
    else:
        # 默认使用mock提供者
        return MockProvider()
