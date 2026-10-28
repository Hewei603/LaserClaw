"""Codex exec transport for LaserClaw's existing task and tool contracts.

Codex only selects structured actions here. LaserClaw still validates and runs
its own tools, records their real results, and owns all case/inventory writes.
"""
from __future__ import annotations

import asyncio
import base64
import json
import os
from pathlib import Path
import shutil
import signal
import subprocess
import tempfile
from threading import RLock
from time import monotonic
from uuid import uuid4

from .openai import OpenAIProvider
from ..config import get_settings
from ..observability.usage import attach_usage_payload

_STATUS_LOCK = RLock()
_STATUS_CACHE: dict[tuple, tuple[float, dict]] = {}
_JSON_SCHEMA = {
    "type": "object",
    "properties": {"response_json": {"type": "string"}},
    "required": ["response_json"],
    "additionalProperties": False,
}
_IMAGE_EXTENSIONS = {
    "image/png": ".png", "image/jpeg": ".jpg", "image/webp": ".webp", "image/gif": ".gif",
}


def resolve_command(configured_path: str = "") -> list[str]:
    """Prefer native executables; run npm shims through Node without a shell."""
    name = configured_path.strip() or "codex"
    if configured_path.strip():
        candidate = shutil.which(name)
        if candidate is None and Path(name).is_file():
            candidate = str(Path(name).resolve())
    else:
        candidate = (shutil.which("codex.exe") if os.name == "nt" else None) or shutil.which(name)
    if not candidate:
        raise RuntimeError("未找到 Codex CLI。请在后端所在电脑安装 Codex CLI，或填写可执行文件路径。")
    path = Path(candidate)
    if path.suffix.lower() in {".cmd", ".bat", ".ps1", ".js"}:
        script = path if path.suffix.lower() == ".js" else path.parent / "node_modules/@openai/codex/bin/codex.js"
        node = shutil.which("node")
        if not node or not script.is_file():
            raise RuntimeError("无法启动 Codex 包装脚本。请填写 codex.exe 路径，或安装 Node.js 和官方 Codex CLI。")
        return [node, str(script)]
    return [str(path)]


def _environment() -> dict[str, str]:
    env = os.environ.copy()
    # The subscription option must never silently use API-key billing.
    for key in ("OPENAI_API_KEY", "CODEX_API_KEY", "CODEX_THREAD_ID", "CODEX_TURN_ID"):
        env.pop(key, None)
    return env


def _hidden_process_options() -> dict:
    return {"creationflags": subprocess.CREATE_NO_WINDOW} if os.name == "nt" else {}


def codex_status(*, refresh: bool = False, path: str | None = None) -> dict:
    """Check availability/sign-in without inference or exposing credential text."""
    settings = get_settings()
    configured = settings.codex_exec_path if path is None else path
    key = (configured, os.environ.get("PATH", ""), os.environ.get("CODEX_HOME", ""))
    with _STATUS_LOCK:
        cached = _STATUS_CACHE.get(key)
        if not refresh and cached and monotonic() - cached[0] < 15:
            return dict(cached[1])
    status = {"available": False, "logged_in": False, "ready": False, "auth_method": None,
              "version": None, "executable": None, "message": ""}
    try:
        command = resolve_command(configured)
        status["available"], status["executable"] = True, command[-1]
        options = dict(capture_output=True, timeout=8, env=_environment(), **_hidden_process_options())
        version = subprocess.run([*command, "--version"], **options)
        if version.returncode != 0:
            raise RuntimeError("Codex CLI 无法运行，请检查安装或可执行文件路径。")
        status["version"] = version.stdout.decode("utf-8", errors="replace").strip()[:120]
        auth = subprocess.run([*command, "login", "status"], **options)
        text = (auth.stdout + auth.stderr).decode("utf-8", errors="replace").lower()
        if auth.returncode == 0 and "chatgpt" in text:
            status.update(logged_in=True, ready=True, auth_method="chatgpt",
                          message="已使用 ChatGPT 登录；调用计入该账户的 Codex 订阅额度。")
        elif auth.returncode == 0 and ("api key" in text or "api_key" in text):
            status.update(logged_in=True, auth_method="api_key",
                          message="CLI 当前使用 API Key 登录。请在后端电脑执行 codex login，改用 ChatGPT 登录后再使用订阅模式。")
        else:
            status["message"] = "Codex CLI 尚未登录。请在后端电脑执行 codex login，完成 ChatGPT 登录后点击刷新状态。"
    except subprocess.TimeoutExpired:
        status["message"] = "检查 Codex CLI 状态超时，请确认 CLI 可以正常启动。"
    except (OSError, RuntimeError) as exc:
        status["message"] = str(exc) if isinstance(exc, RuntimeError) else "无法启动 Codex CLI，请检查可执行文件路径。"
    with _STATUS_LOCK:
        _STATUS_CACHE[key] = (monotonic(), dict(status))
    return status


def _stop_process(process: subprocess.Popen) -> None:
    if process.poll() is not None:
        return
    try:
        if os.name == "nt":
            subprocess.run(["taskkill", "/PID", str(process.pid), "/T", "/F"],
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=5,
                           **_hidden_process_options())
        else:
            os.killpg(process.pid, signal.SIGKILL)
    except (OSError, subprocess.TimeoutExpired):
        pass
    if process.poll() is None:
        process.kill()
    process.wait(timeout=5)


class CodexExecError(RuntimeError):
    """Actionable runtime failure, suitable for the task's persisted trace."""


def _failure_message(text: str) -> str:
    lower = text.lower()
    if any(part in lower for part in ("usage limit", "rate limit", "quota", "usage_limit", "limit reached")):
        return "Codex 订阅额度已用尽或受到限流。请查看 Codex 账户额度，额度恢复后继续；已完成的工具结果保留。"
    if any(part in lower for part in ("unauthorized", "authentication", "not logged", "401", "refresh token")):
        return "Codex 登录已失效。请在后端电脑执行 codex login，重新使用 ChatGPT 登录。"
    if any(part in lower for part in ("model", "unsupported model")):
        return "Codex 执行失败，可能是所选模型不可用或模型配置不受支持。请检查模型 ID、账户权限及 CLI 版本。"
    return "Codex exec 执行失败。请检查 CLI 登录、网络和版本，然后重试；已完成的工具结果保留。"


class CodexExecProvider(OpenAIProvider):
    """Reuse LaserClaw's established task prompts, replacing every API transport."""

    def __init__(self, *, model=None, path=None, timeout=None, reasoning_effort=None):
        settings = get_settings()
        self.model = model or settings.codex_exec_model
        self.configured_path = settings.codex_exec_path if path is None else path
        self.command = resolve_command(self.configured_path)
        self.timeout = int(timeout or settings.codex_exec_timeout_seconds)
        self.reasoning_effort = reasoning_effort or settings.codex_exec_reasoning_effort

    async def _complete(self, prompt: str, *, schema: dict | None = None, images: list[dict] | None = None) -> dict:
        runtime = await asyncio.to_thread(codex_status, path=self.configured_path)
        if not runtime["ready"]:
            raise CodexExecError(runtime["message"])
        with tempfile.TemporaryDirectory(prefix="laserclaw-codex-") as directory:
            root = Path(directory)
            schema_path, answer_path = root / "schema.json", root / "answer.json"
            schema_path.write_text(json.dumps(schema or _JSON_SCHEMA, ensure_ascii=False), encoding="utf-8")
            image_args = []
            for index, picture in enumerate(images or []):
                mime, encoded = picture["data_url"].split(";base64,", 1)
                suffix = _IMAGE_EXTENSIONS.get(mime.removeprefix("data:"))
                if not suffix:
                    raise CodexExecError("Codex 图片格式不受支持，请使用 PNG、JPEG、WebP 或 GIF。")
                path = root / f"image-{index + 1}{suffix}"
                path.write_bytes(base64.b64decode(encoded, validate=True))
                image_args.extend(["--image", str(path)])
            command = [
                *self.command, "exec", "--ignore-user-config", "--ephemeral", "--skip-git-repo-check",
                "--sandbox", "read-only", "--color", "never", "--json", "--model", self.model,
                "-c", 'model_provider="openai"', "-c", 'forced_login_method="chatgpt"',
                "-c", 'approval_policy="never"', "-c", "project_doc_max_bytes=0",
                "-c", f"model_reasoning_effort={json.dumps(self.reasoning_effort)}",
                "--disable", "shell_tool", "--disable", "apply_patch_freeform", "--disable", "multi_agent",
                "--output-schema", str(schema_path), "--output-last-message", str(answer_path),
                *image_args, "-",
            ]
            process = subprocess.Popen(
                command, cwd=root, env=_environment(), stdin=subprocess.PIPE,
                stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                **(_hidden_process_options() if os.name == "nt" else {"start_new_session": True}),
            )
            try:
                stdout, stderr = await asyncio.to_thread(
                    process.communicate, input=prompt.encode("utf-8"), timeout=self.timeout,
                )
            except subprocess.TimeoutExpired:
                await asyncio.to_thread(_stop_process, process)
                raise CodexExecError(f"Codex 本轮执行超过 {self.timeout} 秒。可在首页增加等待时间后继续；此前工具结果保留。") from None
            except asyncio.CancelledError:
                await asyncio.to_thread(_stop_process, process)
                raise
            events, usage, errors, completed = [], {}, [], False
            for line in stdout.decode("utf-8", errors="replace").splitlines():
                try:
                    event = json.loads(line)
                except ValueError:
                    continue
                if not isinstance(event, dict):
                    continue
                events.append(event)
                if event.get("type") == "turn.completed":
                    completed, usage = True, event.get("usage") or {}
                if event.get("type") in {"error", "turn.failed"}:
                    errors.append(str(event.get("message") or event.get("error") or "Codex turn failed"))
            if process.returncode != 0 or errors or not completed:
                raise CodexExecError(_failure_message("\n".join(errors) + stderr.decode("utf-8", errors="replace")))
            # This adapter never delegates execution to Codex's shell or MCPs.
            if any(e.get("item", {}).get("type") in {"command_execution", "file_change", "mcp_tool_call"}
                   for e in events):
                raise CodexExecError("Codex 返回了适配器之外的执行操作；本轮结果未被采纳，请检查 CLI 配置。")
            try:
                answer = json.loads(answer_path.read_text(encoding="utf-8"))
                if not isinstance(answer, dict):
                    raise ValueError
            except (OSError, ValueError):
                raise CodexExecError("Codex 未返回完整的结构化结果；请重试，本轮不会伪造工具结果。") from None
            return attach_usage_payload(answer, provider="codex_exec", model=self.model, usage=usage)

    async def _request_json(self, instructions: str, context, images: list[dict] | None = None) -> dict:
        prompt = (
            "You are LaserClaw's model backend. Respond directly using the supplied context and images. "
            "Do not inspect the computer or execute commands. Do not use external tools. "
            "Return a JSON object with response_json containing the complete task result encoded as a JSON string. "
            "Do not invent measurements or computed physics. Match the user's language.\n\n"
            f"Task instructions:\n{instructions}\n\nContext:\n{json.dumps(context, ensure_ascii=False)}"
        )
        response = await self._complete(prompt, images=images)
        try:
            result = json.loads(response["response_json"])
            if not isinstance(result, dict):
                raise ValueError
        except (KeyError, TypeError, ValueError):
            raise CodexExecError("Codex 返回的任务 JSON 不完整；请重试。") from None
        result.update(model_provider="codex_exec", model=self.model, _usage=response["_usage"])
        return result

    async def _generate_json(self, task_name, case_data, output_instructions):
        return await self._request_json(
            f"Task: {task_name}\n{output_instructions}\n"
            "Use only provided or tool-computed numerical facts; mark unknowns explicitly.",
            case_data,
        )

    async def _generate_multimodal_json(self, system_prompt, user_text, data_url, task_name):
        return await self._request_json(f"{system_prompt}\n{user_text}\nTask: {task_name}", {},
                                        [{"data_url": data_url}])

    async def extract_design_facts(self, context: dict, images: list[dict]) -> dict:
        from ..design.brief import extraction_prompt

        pictures = [{"data_url": f"data:{item['mime']};base64,{base64.b64encode(item['data']).decode('ascii')}"}
                    for item in images]
        sources = [f"image:{item['id']}" for item in images]
        return await self._request_json(extraction_prompt(), {"context": context, "image_sources_in_order": sources}, pictures)

    async def agent_turn(self, instructions, messages, tools):
        if not tools:
            raise CodexExecError("本轮没有可用的 LaserClaw 工具。")
        schema = {
            "type": "object",
            "properties": {"calls": {"type": "array", "minItems": 1, "maxItems": 1, "items": {
                "type": "object",
                "properties": {"name": {"type": "string", "enum": [t["name"] for t in tools]},
                               "arguments": {"type": "string"}},
                "required": ["name", "arguments"], "additionalProperties": False,
            }}},
            "required": ["calls"], "additionalProperties": False,
        }
        pictures, history = [], []
        for message in messages:
            entry = {key: value for key, value in message.items() if key != "images"}
            if "items" in entry:
                entry["items"] = [item for item in entry["items"] if item.get("type") not in {"reasoning"}]
            if message.get("images"):
                entry["attached_image_ids"] = [img.get("id") for img in message["images"]]
                for picture in message["images"]:
                    pictures.append(picture)
            history.append(entry)
        prompt = (
            f"{instructions}\n\n"
            "TRANSPORT CONTRACT: You select the next LaserClaw tool call, which the application will validate and run. "
            "You must NOT execute the tool yourself or invent a result. Do not inspect files, run shell commands, or "
            "use your own tools. Select exactly ONE available tool. Encode its complete arguments as a JSON string. "
            "The history contains real tool responses. Use them to decide the next action; call finish to deliver "
            "a completed, partial, or needs_input result. Attached images follow history order.\n\n"
            f"Available tool definitions:\n{json.dumps(tools, ensure_ascii=False)}\n\n"
            f"Conversation and real tool results:\n{json.dumps(history, ensure_ascii=False)}"
        )
        response = await self._complete(prompt, schema=schema, images=pictures)
        calls, items = [], []
        allowed = {tool["name"] for tool in tools}
        raw_calls = response.get("calls")
        if not isinstance(raw_calls, list) or len(raw_calls) != 1:
            raise CodexExecError("Codex 未返回单个有效工具请求。")
        for call in raw_calls:
            if not isinstance(call, dict) or call.get("name") not in allowed or not isinstance(call.get("arguments"), str):
                raise CodexExecError("Codex 返回了未知工具或无效参数。")
            # Argument validation/recovery is deliberately owned by the normal tool loop.
            call_id = f"codex_{uuid4().hex}"
            calls.append({"id": call_id, "name": call["name"], "arguments": call["arguments"]})
            items.append({"type": "function_call", "call_id": call_id,
                          "name": call["name"], "arguments": call["arguments"]})
        return {"calls": calls, "items": items, "_usage": response["_usage"]}
