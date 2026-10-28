"""Persist UI model settings alongside the application's durable upload data."""
from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from threading import RLock

# Suggestions start with the models already supported by the application.
# The UI also accepts an arbitrary model ID for compatible endpoints.
PROVIDERS = {
    "mock": "Mock",
    "codex_exec": "Codex exec · ChatGPT 订阅",
    "deepseek": "DeepSeek",
    "qwen": "Qwen · 通义千问",
    "zhipu": "GLM · 智谱",
    "moonshot": "Kimi · Moonshot",
    "openai": "OpenAI / Compatible API",
    "anthropic": "Anthropic · Claude",
}
COMPATIBLE_PROVIDERS = {"openai", "deepseek", "qwen", "zhipu", "moonshot"}
MODEL_SUGGESTIONS = {
    "codex_exec": ["gpt-6.1-sol"],
    "deepseek": ["deepseek-chat", "deepseek-reasoner"],
    "qwen": ["qwen-plus", "qwen-turbo"],
    "zhipu": ["glm-4-plus"],
    "moonshot": ["moonshot-v1-8k"],
    "openai": ["gpt-6.1-sol", "gpt-4o-mini", "gpt-4o"],
    "anthropic": ["claude-sonnet-4-5"],
}
ALLOWED_FIELDS = {"ai_provider"} | {
    f"{provider}_{field}"
    for provider in PROVIDERS if provider not in {"mock", "codex_exec"}
    for field in ("api_key", "model")
} | {f"{provider}_base_url" for provider in COMPATIBLE_PROVIDERS} | {
    "codex_exec_model", "codex_exec_path", "codex_exec_timeout_seconds", "codex_exec_reasoning_effort",
}
SETTINGS_LOCK = RLock()


def settings_path(settings) -> Path:
    return (
        Path(settings.agent_settings_file)
        if settings.agent_settings_file
        else Path(settings.upload_dir) / ".agent-settings.json"
    )


def read_overrides(settings) -> dict:
    path = settings_path(settings)
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(data, dict) or any(
            key not in ALLOWED_FIELDS or (
                not (type(value) is int and 30 <= value <= 1800)
                if key == "codex_exec_timeout_seconds" else not isinstance(value, str)
            )
            for key, value in data.items()
        ):
            raise ValueError("Invalid settings document")
        if data.get("ai_provider", "mock") not in PROVIDERS:
            raise ValueError("Unknown provider")
        return data
    except (ValueError, OSError) as exc:
        # Never include file contents (which contain credentials) in errors.
        raise RuntimeError(f"Cannot read Agent settings: {path}") from exc


def write_overrides(settings, data: dict) -> None:
    """Atomic replacement: failed writes leave the previous configuration intact."""
    path = settings_path(settings)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w", encoding="utf-8", dir=path.parent,
            prefix=".agent-settings-", suffix=".tmp", delete=False,
        ) as handle:
            temporary = Path(handle.name)
            json.dump(data, handle, ensure_ascii=False, indent=2)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
