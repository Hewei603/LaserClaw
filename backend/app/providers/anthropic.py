"""Anthropic Claude AI provider."""
from __future__ import annotations

import asyncio
import base64
import json
import logging
from typing import Any, Dict, List, Optional

from .base import AIProvider
from ..config import get_settings
from ..observability.usage import attach_usage_payload

try:
    from anthropic import Anthropic, APIConnectionError, APIStatusError, APITimeoutError, RateLimitError

    ANTHROPIC_RETRYABLE_ERRORS = (
        APIConnectionError,
        APITimeoutError,
        RateLimitError,
        APIStatusError,
    )
except ImportError:
    Anthropic = None
    ANTHROPIC_RETRYABLE_ERRORS = ()


logger = logging.getLogger(__name__)

SUPPORTED_IMAGE_MEDIA_TYPES = {"image/jpeg", "image/png", "image/gif", "image/webp"}


class AnthropicProvider(AIProvider):
    """AI provider backed by Anthropic's native Messages API."""

    def __init__(
        self,
        api_key: Optional[str] = None,
        model: Optional[str] = None,
        max_tokens: Optional[int] = None,
        temperature: Optional[float] = None,
    ):
        settings = get_settings()
        self.api_key = api_key or settings.anthropic_api_key
        self.model = model or settings.anthropic_model
        self.max_tokens = max_tokens or settings.anthropic_max_tokens
        self.temperature = settings.anthropic_temperature if temperature is None else temperature

        if not self.api_key:
            raise ValueError("ANTHROPIC_API_KEY is required when AI_PROVIDER=anthropic")
        if Anthropic is None:
            raise RuntimeError("The anthropic package is not installed. Run pip install -r requirements.txt.")

        self.client = Anthropic(api_key=self.api_key)

    async def generate_plan(self, case_data: Dict[str, Any]) -> Dict[str, Any]:
        return await self._create_json_message(
            self._system_prompt(),
            self._case_prompt(
                "Generate a laser experiment plan.",
                case_data,
                """
Return JSON with this shape:
{
  "title": "short plan title",
  "objective": "experiment objective",
  "steps": [{"step": 1, "description": "clear advisory step", "estimated_time": "time estimate"}],
  "parameters_to_check": ["parameter"],
  "safety_notes": ["note"],
  "expected_outputs": ["output"],
  "model_provider": "anthropic",
  "model": "model name"
}
""",
            ),
        )

    async def generate_rezonator_schema(self, case_data: Dict[str, Any]) -> Dict[str, Any]:
        return await self._create_json_message(
            self._system_prompt(),
            self._case_prompt(
                "Generate a ReZonator schema/script draft for manual validation.",
                case_data,
                """
Return JSON with this shape:
{
  "cavity_type": "linear|ring|bow-tie|custom",
  "elements": [{"type": "mirror|crystal|lens|other", "name": "M1", "position": null}],
  "position_source": "case data | to be computed by the cavity_design module",
  "assumptions": ["assumption"],
  "rezonator_script_draft": "draft text or pseudocode",
  "validation_checks": ["check"],
  "model_provider": "anthropic",
  "model": "model name"
}
""",
            ),
        )

    async def generate_troubleshooting(self, symptoms: List[str], case_data: Dict[str, Any]) -> Dict[str, Any]:
        prompt_data = dict(case_data)
        prompt_data["symptoms"] = symptoms
        return await self._create_json_message(
            self._system_prompt(),
            self._case_prompt(
                "Generate laser experiment troubleshooting guidance.",
                prompt_data,
                """
Return JSON with this shape:
{
  "symptoms": ["symptom"],
  "likely_causes": [{"cause": "cause", "rationale": "why it fits", "priority": "High|Medium|Low"}],
  "diagnostic_steps": [{"step": 1, "description": "safe diagnostic step"}],
  "quick_checks": ["check"],
  "risk_notes": ["note"],
  "model_provider": "anthropic",
  "model": "model name"
}
""",
            ),
        )

    async def generate_report(self, case_data: Dict[str, Any]) -> Dict[str, Any]:
        return await self._create_json_message(
            self._system_prompt(),
            self._case_prompt(
                "Generate a structured laser experiment report draft.",
                case_data,
                """
Return JSON with this shape:
{
  "title": "report title",
  "summary": "brief summary",
  "setup": "setup description",
  "observations": ["only what the case data records; say so if nothing recorded"],
  "hypotheses": ["unverified inference (clearly labelled)"],
  "analysis": "analysis draft grounded in the recorded data",
  "next_steps": ["next step"],
  "model_provider": "anthropic",
  "model": "model name"
}
""",
            ),
        )

    async def generate_chat_response(self, context: Dict[str, Any]) -> Dict[str, Any]:
        return await self._create_json_message(
            self._system_prompt(
                "You are chatting with a user about one laser experiment case and retrieved lab knowledge."
            ),
            self._case_prompt(
                "Answer the user's chat message using case context, chat history, and retrieved knowledge.",
                context,
                """
Return JSON with this shape:
{
  "message": "direct assistant reply for the user",
  "summary": "brief internal summary",
  "safety_notes": ["note"],
  "follow_up_questions": ["question if needed"],
  "model_provider": "anthropic",
  "model": "model name"
}
""",
            ),
        )

    async def analyze_image(self, image_data: bytes, mime_type: str, context: Dict[str, Any]) -> Dict[str, Any]:
        normalized_mime = (mime_type or "").split(";")[0].strip().lower()
        if normalized_mime not in SUPPORTED_IMAGE_MEDIA_TYPES:
            return {
                "error": "unsupported_image_mime_type",
                "message": (
                    "Claude Vision supports image/jpeg, image/png, image/gif, and image/webp. "
                    f"Received {mime_type or 'unknown'}."
                ),
                "supported_media_types": sorted(SUPPORTED_IMAGE_MEDIA_TYPES),
                "model_provider": "anthropic",
                "model": self.model,
            }

        system_prompt = self._system_prompt(
            "You analyze laser experiment images, optical layouts, beam profiles, and simulation drawings."
        )
        text_prompt = (
            "Analyze this image for a laser experiment workflow. "
            "State uncertainty, do not infer unsafe operating instructions, and return only valid JSON.\n\n"
            f"Context JSON:\n{json.dumps(context, ensure_ascii=False, indent=2)}\n\n"
            """
Return JSON with this shape:
{
  "image_type": "photo|simulation|beam_profile|diagram|unknown",
  "visible_components": ["component"],
  "possible_laser_setup_interpretation": "interpretation",
  "beam_or_alignment_observations": ["observation"],
  "potential_issues": ["issue"],
  "recommended_next_checks": ["check"],
  "confidence": "high|medium|low",
  "model_provider": "anthropic",
  "model": "model name"
}
"""
        )
        content = [
            {
                "type": "image",
                "source": {
                    "type": "base64",
                    "media_type": normalized_mime,
                    "data": base64.b64encode(image_data).decode("ascii"),
                },
            },
            {"type": "text", "text": text_prompt},
        ]
        return await self._create_json_message(system_prompt, content)

    async def _create_json_message(self, system_prompt: str, user_prompt: str | list[dict[str, Any]]) -> dict:
        raw_text, usage = await self._send_message(system_prompt, user_prompt)
        try:
            result = self._extract_json(raw_text)
        except Exception as exc:
            result = await self._repair_json(raw_text, exc)
        result.setdefault("model_provider", "anthropic")
        result.setdefault("model", self.model)
        return attach_usage_payload(result, provider="anthropic", model=self.model, usage=usage)

    def _extract_json(self, text: str) -> dict:
        if not text or not text.strip():
            raise RuntimeError("Anthropic returned an empty response")

        cleaned = text.strip()
        if cleaned.startswith("```"):
            lines = cleaned.splitlines()
            if lines and lines[0].startswith("```"):
                lines = lines[1:]
            if lines and lines[-1].startswith("```"):
                lines = lines[:-1]
            cleaned = "\n".join(lines).strip()

        result = json.loads(cleaned)
        if not isinstance(result, dict):
            raise RuntimeError("Anthropic response JSON must be an object")
        return result

    async def _repair_json(self, raw_text: str, error: Exception) -> dict:
        repair_prompt = (
            "The previous response was not valid JSON. Repair it and return only the corrected JSON object. "
            "Do not include markdown, explanations, or code fences.\n\n"
            f"JSON parse error: {type(error).__name__}: {str(error)[:500]}\n\n"
            f"Raw response:\n{raw_text[:6000]}"
        )
        repaired_text, _ = await self._send_message(self._system_prompt(), repair_prompt)
        try:
            return self._extract_json(repaired_text)
        except Exception as repair_error:
            raise RuntimeError(
                f"Anthropic returned invalid JSON after repair: {type(repair_error).__name__}"
            ) from repair_error

    async def _send_message(self, system_prompt: str, user_prompt: str | list[dict[str, Any]]) -> tuple[str, dict[str, Any]]:
        last_error: BaseException | None = None
        for attempt in range(2):
            try:
                response = await asyncio.to_thread(
                    self.client.messages.create,
                    model=self.model,
                    max_tokens=self.max_tokens,
                    temperature=self.temperature,
                    system=system_prompt,
                    messages=[{"role": "user", "content": user_prompt}],
                )
                usage = getattr(response, "usage", None)
                usage_payload = {
                    "input_tokens": getattr(usage, "input_tokens", None),
                    "output_tokens": getattr(usage, "output_tokens", None),
                }
                return self._message_text(response), usage_payload
            except ANTHROPIC_RETRYABLE_ERRORS as exc:
                last_error = exc
                logger.warning(
                    "Anthropic call failed: attempt=%s error_type=%s error=%s",
                    attempt + 1,
                    type(exc).__name__,
                    str(exc)[:500],
                )
                if attempt == 0:
                    await asyncio.sleep(1)
                    continue
            except Exception as exc:
                last_error = exc
                logger.exception("Unexpected Anthropic provider error")
                if attempt == 0:
                    await asyncio.sleep(1)
                    continue

        raise RuntimeError(
            f"Anthropic provider failed after retry: {type(last_error).__name__}: {str(last_error)[:500]}"
        )

    @staticmethod
    def _message_text(response: Any) -> str:
        parts: list[str] = []
        for block in getattr(response, "content", []) or []:
            text = getattr(block, "text", None)
            if text is None and isinstance(block, dict):
                text = block.get("text")
            if text:
                parts.append(text)
        return "\n".join(parts).strip()

    def _case_prompt(self, task: str, case_data: Dict[str, Any], output_instructions: str) -> str:
        return (
            f"Task: {task}\n\n"
            f"Case data JSON:\n{json.dumps(case_data, ensure_ascii=False, indent=2)}\n\n"
            f"{output_instructions.strip()}\n\n"
            f'Set "model_provider" to "anthropic" and "model" to "{self.model}".'
        )

    @staticmethod
    def _system_prompt(extra: str = "") -> str:
        base = (
            "You are LaserClaw's laser experiment assistant. "
            "Generate practical, safety-conscious advisory content for laser experiment workflows. "
            "Write every human-readable value in the SAME language as the case "
            "title/description/goal (Chinese case -> Chinese output). JSON keys stay in English. "
            "Never invent numeric physics values (lengths, angles, spot sizes, "
            "reflectivities) or measurements that were not provided: use the case data, "
            "otherwise say the value must be computed or measured. "
            "Do not copy the placeholder values shown in the output schema. "
            "Never claim to operate hardware. Return only valid JSON with no markdown or prose outside JSON."
        )
        return f"{base} {extra}".strip()

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
        result = await self._create_json_message(self._system_prompt(), user_prompt)
        return {
            "summary": str(result.get("summary", "")),
            "memories": result.get("memories") or [],
        }
