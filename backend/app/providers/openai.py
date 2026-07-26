"""
OpenAI AI provider.
"""
import asyncio
import base64
import json
import logging
from typing import Any, Dict, List, Optional

from .base import AIProvider
from ..config import get_settings
from ..observability.usage import attach_usage_payload

try:
    from openai import (
        APIConnectionError,
        APITimeoutError,
        AuthenticationError,
        InternalServerError,
        PermissionDeniedError,
        RateLimitError,
    )

    # Transient failures only. The base APIError must NOT be here: it is the
    # parent of AuthenticationError/PermissionDeniedError, which never fix
    # themselves — retrying them just delays a misleading "service unavailable".
    OPENAI_RETRYABLE_ERRORS = (
        APIConnectionError,
        APITimeoutError,
        RateLimitError,
        InternalServerError,
    )
    OPENAI_FATAL_ERRORS = (AuthenticationError, PermissionDeniedError)
except ImportError:
    OPENAI_RETRYABLE_ERRORS = ()
    OPENAI_FATAL_ERRORS = ()


logger = logging.getLogger(__name__)


class OpenAIProvider(AIProvider):
    """AI provider backed by the OpenAI Chat Completions API."""

    def __init__(
        self,
        api_key: Optional[str] = None,
        model: Optional[str] = None,
        base_url: Optional[str] = None,
    ):
        settings = get_settings()
        self.api_key = api_key or settings.openai_api_key
        self.model = model or settings.openai_model
        self.base_url = base_url or settings.openai_base_url

        if not self.api_key:
            raise ValueError("OPENAI_API_KEY is required when AI_PROVIDER=openai")

        try:
            from openai import OpenAI
        except ImportError as exc:
            raise RuntimeError(
                "The openai package is not installed. Run pip install -r requirements.txt."
            ) from exc

        client_kwargs = {"api_key": self.api_key}
        if self.base_url:
            client_kwargs["base_url"] = self.base_url

        self.client = OpenAI(**client_kwargs)

    async def generate_plan(self, case_data: Dict[str, Any]) -> Dict[str, Any]:
        return await self._generate_json(
            "experiment plan",
            case_data,
            """

If the case data contains "computed_physics" with available=true, those numbers
come from LaserClaw's deterministic physics kernel and are AUTHORITATIVE: quote
the cavity length, waist, spot sizes, element positions and phase-matching
angles exactly as given (with units), and reference them in the setup and steps.
Never replace them with your own estimate. If available=false, say the geometry
still has to be computed with the cavity_design module.

Return JSON with exactly these fields:
{
  "objective": "clear experiment objective",
  "computed_parameters": {"cavity_length_mm": null, "waist_w0_mm": null, "phase_match_angle_deg": null},
  "setup": "equipment and optical setup description",
  "steps": ["step 1 description", "step 2 description"],
  "measurements": ["measurement 1", "measurement 2"],
  "risks": ["safety risk 1", "mitigation"],
  "next_actions": ["follow-up action 1"]
}
""",
        )

    async def generate_troubleshooting(
        self, symptoms: List[str], case_data: Dict[str, Any]
    ) -> Dict[str, Any]:
        prompt_data = dict(case_data)
        prompt_data["symptoms"] = symptoms

        return await self._generate_json(
            "laser experiment troubleshooting advice",
            prompt_data,
            """
Return JSON with exactly these fields:
{
  "symptom": "primary observed symptom",
  "possible_causes": ["cause 1", "cause 2"],
  "diagnostic_checks": ["check 1", "check 2"],
  "recommended_actions": ["action 1", "action 2"],
  "expected_observations": ["expected result after fix"],
  "safety_notes": ["safety precaution 1"]
}
""",
        )

    async def generate_report(self, case_data: Dict[str, Any]) -> Dict[str, Any]:
        return await self._generate_json(
            "laser experiment report draft",
            case_data,
            """
"observations" and "data_summary" are a LAB RECORD: state ONLY what the case
data actually contains (measurements, symptoms, module results). Never invent a
reading, temperature or spot position that was not provided. Put anything you
infer under "hypotheses" and mark it as unverified; if no data was recorded, say
so explicitly.

Return JSON with exactly these fields:
{
  "title": "report title",
  "background": "background and motivation for the experiment",
  "method": "experimental method and procedure",
  "observations": "only what the case data records; say so if nothing recorded",
  "data_summary": "summary of the provided measurements only",
  "hypotheses": ["unverified inference (clearly labelled)"],
  "conclusion": "conclusions supported by the recorded data",
  "next_steps": ["recommended next step 1", "recommended next step 2"]
}
""",
        )

    async def generate_chat_response(self, context: Dict[str, Any]) -> Dict[str, Any]:
        return await self._generate_json(
            "case-aware laser experiment chat",
            context,
            """
Return JSON with this shape:
{
  "message": "direct assistant reply for the user",
  "summary": "brief internal summary",
  "safety_notes": ["note"],
  "follow_up_questions": ["question if needed"],
  "model_provider": "openai",
  "model": "model name"
}
""",
        )

    async def analyze_image(self, image_data: bytes, mime_type: str, context: Dict[str, Any]) -> Dict[str, Any]:
        system_prompt = (
            "You are LaserClaw's laser experiment visual analysis assistant. "
            "Analyze photos, simulation drawings, beam spots, and optical layouts. "
            "Be safety-conscious, state uncertainty, and return only valid JSON."
        )
        data_url = f"data:{mime_type};base64,{base64.b64encode(image_data).decode('ascii')}"
        user_text = (
            "Analyze this image for a laser experiment case. Return JSON with: "
            "disclaimer, title, image_type_hypothesis, observations[], possible_issues[], "
            "recommended_follow_up[], safety_notes[], confidence. "
            f"Context JSON:\n{json.dumps(context, ensure_ascii=False, indent=2)}"
        )
        return await self._generate_multimodal_json(system_prompt, user_text, data_url, "image analysis")

    async def _generate_json(
        self,
        task_name: str,
        case_data: Dict[str, Any],
        output_instructions: str,
    ) -> Dict[str, Any]:
        system_prompt = (
            "You are LaserClaw's laser experiment assistant. "
            "Generate practical, safety-conscious content for laser cavity experiments. "
            "Keep the response concise. "
            "Write every human-readable value in the SAME language as the case "
            "title/description/goal (Chinese case -> Chinese output). JSON keys stay in English. "
            "Never invent numeric physics values (lengths, angles, spot sizes, "
            "reflectivities): use values given in the case data, otherwise say they "
            "must be computed or measured. "
            "Do not copy the placeholder numbers shown in the output schema. "
            "Return only valid JSON. Do not include markdown or extra prose."
        )

        user_prompt = (
            f"Task: {task_name}\n\n"
            f"Case data JSON:\n{json.dumps(case_data, ensure_ascii=False, indent=2)}\n\n"
            f"{output_instructions.strip()}"
        )

        logger.info(
            "Calling OpenAI provider: task=%s model=%s prompt_chars=%s",
            task_name,
            self.model,
            len(user_prompt),
        )

        last_error: Optional[BaseException] = None

        max_attempts = 2
        for attempt in range(max_attempts):
            try:
                request_kwargs = {
                    "model": self.model,
                    "messages": [
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_prompt},
                    ],
                    "response_format": {"type": "json_object"},
                    "max_completion_tokens": 3000,
                    "timeout": 120,
                }
                if self.model.lower().startswith(("gpt-5", "o1", "o3", "o4")):
                    request_kwargs["reasoning_effort"] = "minimal"

                response = await asyncio.to_thread(
                    self.client.chat.completions.create,
                    **request_kwargs,
                )

                choice = response.choices[0]
                content = choice.message.content
                if not content:
                    logger.error(
                        "OpenAI returned empty content for task=%s finish_reason=%s",
                        task_name,
                        getattr(choice, "finish_reason", None),
                    )
                parsed = self._parse_json_response(content, task_name)
                usage = getattr(response, "usage", None)
                usage_payload = {
                    "input_tokens": getattr(usage, "prompt_tokens", None),
                    "output_tokens": getattr(usage, "completion_tokens", None),
                    "total_tokens": getattr(usage, "total_tokens", None),
                }
                parsed.setdefault("model_provider", "openai")
                parsed.setdefault("model", self.model)
                return attach_usage_payload(parsed, provider="openai", model=self.model, usage=usage_payload)

            except OPENAI_FATAL_ERRORS as exc:
                # Never retryable, and the generic "service unavailable" text
                # would point the user at the wrong cause. Say what it is.
                logger.error("OpenAI auth/permission failure for task=%s: %s", task_name, exc)
                raise RuntimeError(
                    f"API key 无效或无权限:请检查 .env 中的 API key 是否正确、账户是否有余额。"
                    f"(原始错误:{type(exc).__name__})"
                ) from exc

            except OPENAI_RETRYABLE_ERRORS as exc:
                last_error = exc
                logger.warning(
                    "OpenAI call failed: task=%s attempt=%s error_type=%s error=%s",
                    task_name,
                    attempt + 1,
                    type(exc).__name__,
                    str(exc),
                )

                if attempt < max_attempts - 1:
                    await asyncio.sleep(1.5 * (attempt + 1))
                    continue

            except Exception:
                logger.exception("Unexpected OpenAI provider error for task=%s", task_name)
                raise

        raise RuntimeError(
            f"模型服务暂时不可用(已重试 {max_attempts} 次):{type(last_error).__name__}。"
            f"请稍后重试;若持续失败,请检查网络与 .env 配置。"
        )

    @staticmethod
    def _parse_json_response(content: Optional[str], task_name: str) -> Dict[str, Any]:
        if not content or not content.strip():
            raise RuntimeError("OpenAI returned an empty response")

        text = content.strip()
        if text.startswith("```"):
            lines = text.splitlines()
            if lines and lines[0].startswith("```"):
                lines = lines[1:]
            if lines and lines[-1].startswith("```"):
                lines = lines[:-1]
            text = "\n".join(lines).strip()

        try:
            result = json.loads(text)
        except json.JSONDecodeError as exc:
            logger.error(
                "OpenAI returned invalid JSON for task=%s. Raw content=%s",
                task_name,
                content,
            )
            raise RuntimeError("OpenAI returned invalid JSON") from exc

        if not isinstance(result, dict):
            raise RuntimeError("OpenAI response JSON must be an object")

        return result

    async def _generate_multimodal_json(
        self,
        system_prompt: str,
        user_text: str,
        data_url: str,
        task_name: str,
    ) -> Dict[str, Any]:
        logger.info("Calling OpenAI vision provider: task=%s model=%s", task_name, self.model)
        response = await asyncio.to_thread(
            self.client.chat.completions.create,
            model=self.model,
            messages=[
                {"role": "system", "content": system_prompt},
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": user_text},
                        {"type": "image_url", "image_url": {"url": data_url}},
                    ],
                },
            ],
            response_format={"type": "json_object"},
            max_completion_tokens=2500,
            timeout=120,
        )
        parsed = self._parse_json_response(response.choices[0].message.content, task_name)
        usage = getattr(response, "usage", None)
        return attach_usage_payload(
            parsed,
            provider="openai",
            model=self.model,
            usage={
                "input_tokens": getattr(usage, "prompt_tokens", None),
                "output_tokens": getattr(usage, "completion_tokens", None),
                "total_tokens": getattr(usage, "total_tokens", None),
            },
        )

    async def summarize_chat(
        self,
        messages: List[Dict[str, Any]],
        previous_summary: str | None = None,
    ) -> Dict[str, Any]:
        formatted = "\n".join(f"{m['role'].upper()}: {m['content']}" for m in messages)
        user_prompt = (
            f"Previous summary:\n{previous_summary or '(none)'}\n\n"
            f"New messages:\n{formatted[:12000]}\n\n"
            "Summarise the conversation for future laser experiment assistance context. "
            "Return a JSON object with exactly two keys:\n"
            '  "summary": a concise rolling summary string (max 1200 chars),\n'
            '  "memories": a list of objects each with keys '
            '"content" (string), "memory_type" (fact|decision|constraint|preference), '
            '"importance" (integer 1-5).'
        )
        result = await self._generate_json(
            "chat_summarise",
            {"user_prompt": user_prompt},
            user_prompt,
        )
        return {
            "summary": str(result.get("summary", "")),
            "memories": result.get("memories") or [],
        }
