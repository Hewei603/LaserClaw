"""Rule-first tool router with LLM fallback for intent classification."""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

# ---------------------------------------------------------------------------
# Tool names
# ---------------------------------------------------------------------------
TOOL_CHAT = "chat"
TOOL_PLAN = "generate_plan"
TOOL_TROUBLESHOOTING = "generate_troubleshooting"
TOOL_REPORT = "generate_report"
TOOL_RESONATOR = "generate_resonator_draft"
TOOL_STABILITY = "run_stability_analysis"
TOOL_BEAM_PROFILE = "run_beam_profile_analysis"
TOOL_SPECTRUM = "run_spectrum_analysis"
TOOL_COMPONENTS = "generate_component_list"
TOOL_MODULE_MANAGEMENT = "manage_case_modules"

ALL_TOOLS = [
    TOOL_CHAT,
    TOOL_PLAN,
    TOOL_TROUBLESHOOTING,
    TOOL_REPORT,
    TOOL_RESONATOR,
    TOOL_STABILITY,
    TOOL_BEAM_PROFILE,
    TOOL_SPECTRUM,
    TOOL_COMPONENTS,
    TOOL_MODULE_MANAGEMENT,
]

# ---------------------------------------------------------------------------
# Rule patterns (Chinese + English)
# ---------------------------------------------------------------------------
_PLAN_PATTERNS = [
    r"实验计划", r"实验步骤", r"怎么搭建", r"如何搭建", r"搭建方案",
    r"实验方案", r"实验流程", r"操作步骤", r"怎么做实验", r"怎么做这个实验",
    r"如何进行实验", r"如何进行", r"怎么做",
    r"experiment plan", r"experimental steps", r"how to set up", r"setup guide",
    r"build a setup", r"procedure", r"protocol",
]

_TROUBLESHOOTING_PATTERNS = [
    r"故障", r"不出光", r"功率低", r"功率波动", r"光斑异常", r"光斑",
    r"激光不稳定", r"出不了光", r"没有输出", r"输出不稳定", r"模式跳变",
    r"噪声大", r"频率漂移", r"腔失调", r"准直问题", r"准直有问题", r"准直",
    r"排查", r"光路偏",
    r"troubleshoot", r"no output", r"low power", r"power fluctuation",
    r"beam quality", r"unstable", r"misalignment", r"diagnose", r"not lasing",
    r"mode hopping", r"noise", r"drift",
]

_REPORT_PATTERNS = [
    r"报告", r"总结", r"实验记录整理", r"整理实验记录", r"实验总结", r"写报告",
    r"生成报告", r"整理数据", r"数据总结", r"实验结果",
    r"report", r"summary", r"summarize", r"write up", r"experiment record",
    r"data summary", r"results summary",
]

_RESONATOR_PATTERNS = [
    r"rezonator", r"腔稳定性", r"腔长", r"曲率半径", r"仿真输入",
    r"谐振腔", r"腔型设计", r"腔模", r"beam waist", r"腔参数",
    r"resonator", r"cavity stability", r"cavity length", r"radius of curvature",
    r"simulation input", r"cavity design", r"mode calculation",
]

_STABILITY_PATTERNS = [
    r"稳定性测量", r"功率稳定性", r"功率计读数", r"功率计照片", r"OCR读数", r"ocr读数",
    r"稳定性报告", r"power meter OCR", r"power stability report", r"stability report",
]

_BEAM_PROFILE_PATTERNS = [
    r"光斑分析", r"光斑直径", r"光斑半径", r"椭圆度", r"BeamGage", r"beamgage",
    r"beam profile", r"beam spot", r"spot size", r"ellipticity",
]

_SPECTRUM_PATTERNS = [
    r"光谱", r"中心波长", r"峰值波长", r"谱宽", r"半高宽", r"FWHM", r"fwhm",
    r"spectrum", r"spectral", r"linewidth",
]

_COMPONENT_PATTERNS = [
    r"器件清单", r"元件清单", r"采购表", r"采购清单", r"已有器件", r"需要采购",
    r"component list", r"equipment list", r"procurement", r"bill of materials", r"BOM",
]

_MODULE_PATTERNS = [
    r"模块", r"添加模块", r"更改模块", r"删除模块", r"case module", r"module",
]


def _compile(patterns: list[str]) -> re.Pattern[str]:
    return re.compile("|".join(patterns), re.IGNORECASE)


_RE_PLAN = _compile(_PLAN_PATTERNS)
_RE_TROUBLESHOOTING = _compile(_TROUBLESHOOTING_PATTERNS)
_RE_REPORT = _compile(_REPORT_PATTERNS)
_RE_RESONATOR = _compile(_RESONATOR_PATTERNS)
_RE_STABILITY = _compile(_STABILITY_PATTERNS)
_RE_BEAM_PROFILE = _compile(_BEAM_PROFILE_PATTERNS)
_RE_SPECTRUM = _compile(_SPECTRUM_PATTERNS)
_RE_COMPONENTS = _compile(_COMPONENT_PATTERNS)
_RE_MODULES = _compile(_MODULE_PATTERNS)


# ---------------------------------------------------------------------------
# Result dataclass
# ---------------------------------------------------------------------------
@dataclass
class RouteResult:
    selected_tool: str
    confidence: float          # 0.0 – 1.0
    reason: str
    rule_matched: bool
    fallback_used: bool
    matched_pattern: str | None = None


# ---------------------------------------------------------------------------
# Rule-first router
# ---------------------------------------------------------------------------
def _rule_route(text: str) -> RouteResult | None:
    """Return a RouteResult if a high-confidence rule fires, else None."""
    matches: list[tuple[str, re.Match[str]]] = []

    for tool, pattern in [
        (TOOL_STABILITY, _RE_STABILITY),
        (TOOL_BEAM_PROFILE, _RE_BEAM_PROFILE),
        (TOOL_SPECTRUM, _RE_SPECTRUM),
        (TOOL_COMPONENTS, _RE_COMPONENTS),
        (TOOL_MODULE_MANAGEMENT, _RE_MODULES),
        (TOOL_RESONATOR, _RE_RESONATOR),
        (TOOL_TROUBLESHOOTING, _RE_TROUBLESHOOTING),
        (TOOL_REPORT, _RE_REPORT),
        (TOOL_PLAN, _RE_PLAN),
    ]:
        m = pattern.search(text)
        if m:
            matches.append((tool, m))

    if not matches:
        return None

    # If only one rule fires → high confidence
    if len(matches) == 1:
        tool, m = matches[0]
        return RouteResult(
            selected_tool=tool,
            confidence=0.92,
            reason=f"Rule matched: '{m.group()}'",
            rule_matched=True,
            fallback_used=False,
            matched_pattern=m.group(),
        )

    # Multiple rules fire → pick highest-priority (resonator > troubleshooting > report > plan)
    tool, m = matches[0]
    return RouteResult(
        selected_tool=tool,
        confidence=0.75,
        reason=f"Multiple rules matched; selected highest-priority tool. Matched: '{m.group()}'",
        rule_matched=True,
        fallback_used=False,
        matched_pattern=m.group(),
    )


# ---------------------------------------------------------------------------
# LLM / MockProvider fallback
# ---------------------------------------------------------------------------
async def _llm_route(text: str) -> RouteResult:
    """Use the configured AI provider to classify intent when rules are uncertain."""
    try:
        from ..providers import get_ai_provider  # local import to avoid circular deps

        provider = get_ai_provider()
        prompt_context: dict[str, Any] = {
            "user_request": text,
            "task": (
                "Classify the user request into exactly one of these tools: "
                f"{ALL_TOOLS}. "
                "Reply with JSON: {{\"tool\": \"<tool_name>\", \"reason\": \"<one sentence>\"}}."
            ),
        }
        response = await provider.generate_chat_response(prompt_context)
        raw = response.get("content", "") or response.get("message", "")

        # Try to extract JSON from the response
        import json

        json_match = re.search(r'\{[^}]+\}', raw, re.DOTALL)
        if json_match:
            data = json.loads(json_match.group())
            tool = data.get("tool", TOOL_CHAT)
            if tool not in ALL_TOOLS:
                tool = TOOL_CHAT
            return RouteResult(
                selected_tool=tool,
                confidence=0.65,
                reason=data.get("reason", "LLM classification"),
                rule_matched=False,
                fallback_used=True,
            )
    except Exception:
        pass

    # Final fallback: default to chat
    return RouteResult(
        selected_tool=TOOL_CHAT,
        confidence=0.40,
        reason="No rule matched and LLM fallback unavailable; defaulting to chat.",
        rule_matched=False,
        fallback_used=True,
    )


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------
async def route(text: str) -> RouteResult:
    """Route a user query to the appropriate tool.

    Strategy:
    1. Try rule-first matching (fast, deterministic).
    2. If no rule fires, call LLM/MockProvider for intent classification.
    3. If LLM fails, default to chat.
    """
    result = _rule_route(text)
    if result is not None:
        return result
    return await _llm_route(text)


def route_sync(text: str) -> RouteResult:
    """Synchronous rule-only routing (no LLM fallback). Useful for tests."""
    result = _rule_route(text)
    if result is not None:
        return result
    return RouteResult(
        selected_tool=TOOL_CHAT,
        confidence=0.40,
        reason="No rule matched; defaulting to chat.",
        rule_matched=False,
        fallback_used=False,
    )
