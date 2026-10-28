"""Homepage model configuration; credentials are write-only through this API."""
from typing import Literal
from urllib.parse import urlsplit

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field, SecretStr, field_validator

from ..agent_settings import (
    COMPATIBLE_PROVIDERS, MODEL_SUGGESTIONS, PROVIDERS, SETTINGS_LOCK,
    read_overrides, write_overrides,
)
from ..auth.security import Principal, get_current_principal
from ..config import get_settings
from ..providers import provider_status

router = APIRouter()


class AgentSettingsUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    provider: Literal["mock", "codex_exec", "openai", "anthropic", "deepseek", "qwen", "zhipu", "moonshot"]
    model: str = Field(default="", max_length=200)
    api_key: SecretStr | None = None  # omitted/blank means preserve the current key
    base_url: str | None = Field(default=None, max_length=2048)
    executable_path: str | None = Field(default=None, max_length=2048)
    timeout_seconds: int | None = Field(default=None, ge=30, le=1800, strict=True)
    reasoning_effort: Literal["low", "medium", "high", "xhigh", "max", "ultra"] | None = None

    @field_validator("executable_path")
    @classmethod
    def clean_executable_path(cls, value):
        if value is not None and any(char in value for char in "\r\n\0"):
            raise ValueError("Codex 路径不能包含换行或空字符")
        return value.strip() if value is not None else None

    @field_validator("model")
    @classmethod
    def clean_model(cls, value):
        return value.strip()

    @field_validator("base_url")
    @classmethod
    def validate_url(cls, value):
        if value is None or not value.strip():
            return None  # use the current endpoint, including .env customizations
        value = value.strip().rstrip("/")
        try:
            parsed = urlsplit(value)
            if (
                parsed.scheme not in {"http", "https"} or not parsed.hostname
                or parsed.username or parsed.password or parsed.query or parsed.fragment
                or any(char.isspace() for char in value)
            ):
                raise ValueError
            _ = parsed.port
        except ValueError:
            raise ValueError("Base URL 必须是有效的 HTTP(S) 接口地址") from None
        return value


def _check_access(principal: Principal):
    if get_settings().require_auth and principal.role != "admin":
        raise HTTPException(403, "Admin role required to configure the AI provider")


def _snapshot():
    from ..providers.codex_exec import codex_status

    settings = get_settings()
    providers = []
    for name, label in PROVIDERS.items():
        model = getattr(settings, f"{name}_model", "")
        providers.append({
            "id": name,
            "label": label,
            "model": model,
            "models": list(dict.fromkeys([model, *MODEL_SUGGESTIONS.get(name, [])])) if model else [],
            "api_key_configured": bool(getattr(settings, f"{name}_api_key", None)),
            "base_url": (
                getattr(settings, f"{name}_base_url", None) or "https://api.openai.com/v1"
            ) if name in COMPATIBLE_PROVIDERS else None,
        })
    return {"provider": settings.ai_provider.lower(), "providers": providers, "status": provider_status(),
            "codex_exec": {**codex_status(), "configured_path": settings.codex_exec_path,
                           "timeout_seconds": settings.codex_exec_timeout_seconds,
                           "reasoning_effort": settings.codex_exec_reasoning_effort}}


@router.get("/agent")
def get_agent_settings(principal: Principal = Depends(get_current_principal)):
    _check_access(principal)
    return _snapshot()


@router.put("/agent")
def save_agent_settings(payload: AgentSettingsUpdate, principal: Principal = Depends(get_current_principal)):
    _check_access(principal)
    with SETTINGS_LOCK:
        settings = get_settings()
        overrides = read_overrides(settings)
        if payload.provider == "codex_exec":
            if not payload.model:
                raise HTTPException(422, "请填写 Codex 模型 ID")
            if payload.api_key and payload.api_key.get_secret_value().strip():
                raise HTTPException(422, "Codex 订阅模式不接收 API Key，请使用 CLI 的 ChatGPT 登录。")
            overrides["codex_exec_model"] = payload.model
            if payload.executable_path is not None:
                overrides["codex_exec_path"] = payload.executable_path
            if payload.timeout_seconds is not None:
                overrides["codex_exec_timeout_seconds"] = payload.timeout_seconds
            if payload.reasoning_effort is not None:
                overrides["codex_exec_reasoning_effort"] = payload.reasoning_effort
        elif payload.provider != "mock":
            if not payload.model:
                raise HTTPException(422, "请填写模型 ID")
            key = payload.api_key.get_secret_value().strip() if payload.api_key else ""
            if not key and not getattr(settings, f"{payload.provider}_api_key", None):
                raise HTTPException(422, "请填写所选服务商的 API Key")
            if key:
                if len(key) > 8192 or any(char.isspace() for char in key):
                    raise HTTPException(422, "API Key 不能包含空白字符，且长度不能超过 8192")
                overrides[f"{payload.provider}_api_key"] = key
            overrides[f"{payload.provider}_model"] = payload.model
            if payload.base_url is not None and payload.provider in COMPATIBLE_PROVIDERS:
                overrides[f"{payload.provider}_base_url"] = payload.base_url
        overrides["ai_provider"] = payload.provider
        try:
            write_overrides(settings, overrides)
        except OSError:
            raise HTTPException(500, "无法保存 Agent 配置，请检查数据目录是否可写") from None
        get_settings.cache_clear()
        return _snapshot()


@router.get("/agent/codex/status")
def get_codex_status(executable_path: str | None = None, principal: Principal = Depends(get_current_principal)):
    _check_access(principal)
    from ..providers.codex_exec import codex_status

    return codex_status(refresh=True, path=executable_path)


@router.post("/agent/codex/test")
async def test_codex_connection(payload: AgentSettingsUpdate, principal: Principal = Depends(get_current_principal)):
    _check_access(principal)
    if payload.provider != "codex_exec":
        raise HTTPException(422, "此测试仅用于 Codex exec。")
    from ..providers.codex_exec import CodexExecProvider

    try:
        provider = CodexExecProvider(model=payload.model, path=payload.executable_path,
                                     timeout=payload.timeout_seconds, reasoning_effort=payload.reasoning_effort)
        result = await provider._request_json(
            '连接测试。只返回 {"ok":true,"message":"Codex exec 连接成功"}，不使用工具。', {},
        )
        if result.get("ok") is not True:
            raise RuntimeError("Codex 未返回预期测试结果。")
    except (OSError, RuntimeError) as exc:
        raise HTTPException(502, str(exc)) from None
    return {"ok": True, "message": "Codex exec 连接成功，已完成真实模型调用。", "model": provider.model,
            "auth_method": "chatgpt", "usage": result["_usage"]}
