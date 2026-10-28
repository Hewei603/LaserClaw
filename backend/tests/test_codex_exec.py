"""Subscription transport, real tool-loop integration, and explicit failures."""
import asyncio
import base64
import json
from pathlib import Path
import subprocess
from threading import Event
from types import SimpleNamespace

import pytest
from sqlalchemy.orm import sessionmaker

from app.config import get_settings
from app.observability.usage import attach_usage_payload
from app.providers import get_ai_provider, provider_status
from app.providers import codex_exec as module
from app.providers.codex_exec import CodexExecError, CodexExecProvider


READY = {"ready": True, "available": True, "logged_in": True, "auth_method": "chatgpt",
         "message": "ready", "version": "test-cli", "executable": "codex"}


@pytest.fixture
def cli(monkeypatch):
    state = SimpleNamespace(answer={"response_json": '{"message":"已连接"}'}, commands=[], prompts=[],
                            events=[{"type": "turn.completed", "usage": {"input_tokens": 40, "output_tokens": 12}}],
                            stderr=b"", code=0, timeout=False, stopped=False)
    monkeypatch.setattr(module, "resolve_command", lambda path="": ["test-codex"])
    monkeypatch.setattr(module, "codex_status", lambda **kwargs: dict(READY))

    class Process:
        pid = 12345

        def __init__(self, command, **kwargs):
            state.commands.append((command, kwargs))
            self.command = command
            self.returncode = state.code

        def communicate(self, input, timeout):
            if state.timeout:
                raise subprocess.TimeoutExpired(self.command, timeout)
            prompt = input.decode("utf-8")
            state.prompts.append(prompt)
            answer = state.answer(prompt) if callable(state.answer) else state.answer
            if answer is not None:
                Path(self.command[self.command.index("--output-last-message") + 1]).write_text(
                    json.dumps(answer, ensure_ascii=False), encoding="utf-8",
                )
            return "\n".join(json.dumps(e) for e in state.events).encode(), state.stderr

    monkeypatch.setattr(module.subprocess, "Popen", Process)
    monkeypatch.setattr(module, "_stop_process", lambda process: setattr(state, "stopped", True))
    return state


@pytest.mark.asyncio
async def test_cli_transport_is_utf8_isolated_and_not_api_billed(cli, monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "do-not-inherit")
    monkeypatch.setenv("CODEX_API_KEY", "do-not-inherit-either")
    picture = base64.b64encode(b"test image bytes").decode()
    cli.answer = {"response_json": '{"observations":["测试图片"]}'}
    result = await CodexExecProvider()._request_json("读取晶体标签", {}, [{"data_url": f"data:image/png;base64,{picture}"}])
    command, options = cli.commands[-1]
    assert "读取晶体标签" in cli.prompts[-1]
    assert "读取晶体标签" not in command
    assert "OPENAI_API_KEY" not in options["env"] and "CODEX_API_KEY" not in options["env"]
    assert "--image" in command and "--ignore-user-config" in command
    assert command[command.index("--sandbox") + 1] == "read-only"
    assert not Path(options["cwd"]).exists()  # scratch files, including images, cleaned up
    assert result["observations"] == ["测试图片"]
    assert result["model_provider"] == "codex_exec"
    assert result["_usage"]["total_tokens"] == 52
    assert result["_usage"]["cost_estimate_usd"] is None


def test_subscription_usage_is_never_priced_using_api_rates():
    result = attach_usage_payload({}, provider="codex_exec", model="gpt-4o",
                                  usage={"input_tokens": 1000, "output_tokens": 500})
    assert result["_usage"]["cost_estimate_usd"] is None
    assert result["_usage"]["billing_mode"] == "chatgpt_subscription"


@pytest.mark.asyncio
@pytest.mark.parametrize("events,answer,code,error", [
    ([], {"response_json": "{}"}, 0, "执行失败"),
    ([{"type": "turn.failed", "error": {"message": "usage limit reached"}}], None, 1, "订阅额度"),
    ([{"type": "error", "message": "401 authentication failed"}], None, 1, "登录已失效"),
    ([{"type": "turn.completed"}], None, 0, "结构化结果"),
    ([{"type": "turn.completed"}], {"response_json": "broken"}, 0, "JSON"),
    ([{"type": "item.completed", "item": {"type": "command_execution"}}, {"type": "turn.completed"}],
     {"response_json": "{}"}, 0, "执行操作"),
])
async def test_failed_or_incomplete_cli_turn_is_not_accepted(cli, events, answer, code, error):
    cli.events, cli.answer, cli.code = events, answer, code
    with pytest.raises(CodexExecError, match=error):
        await CodexExecProvider()._request_json("test", {})


@pytest.mark.asyncio
async def test_timeout_kills_child_and_preserves_actionable_error(cli):
    cli.timeout = True
    with pytest.raises(CodexExecError, match="超过 300 秒"):
        await CodexExecProvider()._request_json("test", {})
    assert cli.stopped


@pytest.mark.asyncio
async def test_cancellation_stops_child(cli, monkeypatch):
    started, release = Event(), Event()

    def communicate(self, input, timeout):
        started.set()
        release.wait(3)
        return b"", b""

    monkeypatch.setattr(module.subprocess.Popen, "communicate", communicate)

    def stop(process):
        cli.stopped = True
        release.set()

    monkeypatch.setattr(module, "_stop_process", stop)
    task = asyncio.create_task(CodexExecProvider()._request_json("test", {}))
    assert await asyncio.to_thread(started.wait, 2)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert cli.stopped


@pytest.mark.asyncio
async def test_design_images_and_all_generation_methods_reach_cli(cli):
    provider = CodexExecProvider()
    await provider.generate_plan({"title": "真实案例"})
    await provider.generate_troubleshooting(["不出光"], {"title": "排查"})
    await provider.generate_report({"measurements": {"power_w": 1}})
    await provider.generate_chat_response({"message": "如何搭建"})
    await provider.summarize_chat([{"role": "user", "content": "总长11mm"}])
    await provider.analyze_image(b"test png", "image/png", {"case_id": 1})
    cli.answer = {"response_json": '{"facts":[],"notes":[]}'}
    await provider.extract_design_facts({"title": "标签"}, [{"id": 12, "mime": "image/png", "data": b"image"}])
    assert len(cli.commands) == 7
    assert "image:12" in cli.prompts[-1]
    assert "--image" in cli.commands[-1][0]


@pytest.mark.asyncio
async def test_agent_turn_preserves_tool_feedback_and_image_evidence(cli):
    cli.answer = {"calls": [{"name": "finish", "arguments": '{"status":"partial","summary":"已有计算"}'}]}
    result = await CodexExecProvider().agent_turn("instruction", [
        {"role": "assistant", "items": [{"type": "reasoning", "encrypted_content": "opaque-secret"},
                                       {"type": "function_call", "name": "compute", "call_id": "c1"}]},
        {"role": "tool", "call_id": "c1", "content": '{"tool_call_id":27,"result":{"stable":true}}'},
        {"role": "user", "content": "实际附件", "images": [
            {"id": 7, "data_url": "data:image/png;base64," + base64.b64encode(b"img").decode()}]},
    ], [{"name": "finish", "parameters": {}, "description": "finish"}])
    assert "27" in cli.prompts[-1] and "opaque-secret" not in cli.prompts[-1]
    assert "base64" not in cli.prompts[-1]
    assert result["calls"][0]["id"] == result["items"][0]["call_id"]
    assert result["calls"][0]["name"] == "finish"


@pytest.mark.asyncio
@pytest.mark.parametrize("calls", [[], [{"name": "invented", "arguments": "{}"}],
                                  [{"name": "finish", "arguments": {}}]])
async def test_unknown_or_empty_tool_requests_are_rejected(cli, calls):
    cli.answer = {"calls": calls}
    with pytest.raises(CodexExecError):
        await CodexExecProvider().agent_turn("test", [], [{"name": "finish"}])


def test_codex_settings_persist_without_key_and_preserve_api_profile(client, cli):
    client.put("/api/settings/agent", json={"provider": "openai", "model": "old-model", "api_key": "retained-key"})
    response = client.put("/api/settings/agent", json={
        "provider": "codex_exec", "model": "gpt-6.1-sol", "executable_path": "",
        "timeout_seconds": 180, "reasoning_effort": "high",
    })
    assert response.status_code == 200, response.text
    assert "retained-key" not in response.text
    assert response.json()["status"]["effective_provider"] == "codex_exec"
    get_settings.cache_clear()
    assert get_settings().openai_api_key == "retained-key"
    assert get_ai_provider().model == "gpt-6.1-sol"
    assert get_ai_provider().timeout == 180
    assert client.put("/api/settings/agent", json={"provider": "openai", "model": "old-model"}).status_code == 200
    assert get_ai_provider().api_key == "retained-key"


@pytest.mark.parametrize("patch", [{"api_key": "not-a-subscription"}, {"timeout_seconds": 29},
                                  {"timeout_seconds": 1801}, {"timeout_seconds": "300"},
                                  {"executable_path": "codex\nbad"}, {"reasoning_effort": "made-up"}])
def test_invalid_codex_settings_do_not_change_active_provider(client, cli, patch):
    response = client.put("/api/settings/agent", json={"provider": "codex_exec", "model": "test", **patch})
    assert response.status_code == 422
    assert get_settings().ai_provider == "mock"


def test_missing_cli_never_silently_becomes_mock(monkeypatch):
    monkeypatch.setenv("AI_PROVIDER", "codex_exec")
    get_settings.cache_clear()

    def missing(path=""):
        raise RuntimeError("未找到 Codex CLI")

    monkeypatch.setattr(module, "resolve_command", missing)
    with pytest.raises(RuntimeError, match="未找到"):
        get_ai_provider()
    assert provider_status()["is_mock"] is False
    assert provider_status()["effective_provider"] is None


def test_status_never_returns_api_key_from_cli_output(monkeypatch):
    module._STATUS_CACHE.clear()
    monkeypatch.setattr(module, "resolve_command", lambda path="": ["codex"])
    outputs = iter([subprocess.CompletedProcess([], 0, b"codex-cli test", b""),
                    subprocess.CompletedProcess([], 0, b"Logged in using an API key sk-secret", b"")])
    monkeypatch.setattr(module.subprocess, "run", lambda *a, **kw: next(outputs))
    result = module.codex_status(refresh=True)
    assert result["logged_in"] and not result["ready"]
    assert result["auth_method"] == "api_key"
    assert "sk-secret" not in json.dumps(result)


def test_live_test_endpoint_checks_draft_without_saving(client, cli):
    cli.answer = {"response_json": '{"ok":true}'}
    result = client.post("/api/settings/agent/codex/test", json={"provider": "codex_exec", "model": "draft-model"})
    assert result.status_code == 200, result.text
    assert result.json()["model"] == "draft-model"
    assert get_settings().ai_provider == "mock"
    assert result.json()["usage"]["cost_estimate_usd"] is None


def test_workbench_uses_codex_selected_tool_and_real_physics(client, db, cli, monkeypatch):
    from app.workbench import service

    monkeypatch.setattr(service, "SessionLocal", sessionmaker(bind=db.get_bind(), expire_on_commit=False))
    client.put("/api/settings/agent", json={"provider": "codex_exec", "model": "gpt-6.1-sol"})
    case = client.post("/api/cases", json={"title": "Codex工具验收"}).json()
    system = {"mode": "standing_wave", "wavelength_nm": 1064, "elements": [
        {"name": "M1", "kind": "mirror"}, {"name": "air", "kind": "space", "length_mm": 50},
        {"name": "M2", "kind": "mirror", "radius_mm": 100}]}

    def decide(prompt):
        history = json.loads(prompt.split("Conversation and real tool results:\n")[1])
        outputs = [json.loads(m["content"]) for m in history if m["role"] == "tool"]
        if not outputs:
            return {"calls": [{"name": "analyze_optical_system", "arguments": json.dumps(system)}]}
        assert outputs[-1]["result"]["stable_both_planes"] is True
        return {"calls": [{"name": "finish", "arguments": json.dumps({
            "status": "completed", "summary": "已读取真实稳定腔计算。", "evidence_tool_call_ids": [outputs[-1]["tool_call_id"]],
        }, ensure_ascii=False)}]}

    cli.answer = decide
    response = client.post(f"/api/cases/{case['id']}/workbench/runs", json={"message": "计算这个稳定腔"})
    assert response.status_code == 202, response.text
    run = client.get(f"/api/cases/{case['id']}/workbench/runs/{response.json()['task_id']}").json()
    assert run["status"] == "completed", run
    optical = next(t for t in run["tools"] if t["name"] == "analyze_optical_system")
    assert optical["output"]["planes"]["tangential"]["input"]["radius_mm"] == pytest.approx(0.130131, rel=1e-5)
    assert run["result"]["evidence_tool_call_ids"] == [optical["id"]]
    assert len(cli.commands) == 2
