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

ALL_TOOLS = [TOOL_CHAT, TOOL_PLAN, TOOL_TROUBLESHOOTING, TOOL_REPORT, TOOL_RESONATOR]

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


def _compile(patterns: list[str]) -> re.Pattern[str]:
    return re.compile("|".join(patterns), re.IGNORECASE)


_RE_PLAN = _compile(_PLAN_PATTERNS)
_RE_TROUBLESHOOTING = _compile(_TROUBLESHOOTING_PATTERNS)
_RE_REPORT = _compile(_REPORT_PATTERNS)
_RE_RESONATOR = _compile(_RESONATOR_PATTERNS)


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
