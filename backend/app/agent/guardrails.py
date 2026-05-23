"""Laser experiment safety guardrails."""
from __future__ import annotations

HIGH_RISK_TERMS = {
    "bypass safety",
    "disable interlock",
    "directly control",
    "fire laser",
    "high power",
    "高功率",
    "绕过安全",
    "关闭联锁",
}


def assess_risk(goal: str) -> tuple[str, list[str]]:
    """Classify task risk and return required safety reminders."""
    lowered = (goal or "").lower()
    matched = [term for term in HIGH_RISK_TERMS if term.lower() in lowered]
    if matched:
        return "high", [
            "Agent output must remain advisory and cannot operate hardware.",
            "Human review is required before any laser experiment action.",
            "Follow device manuals, local SOPs, PPE, interlocks, and institutional safety rules.",
        ]
    return "medium", [
        "Review all laser safety assumptions before applying generated advice.",
        "Do not bypass manuals, SOPs, interlocks, or human approval gates.",
    ]
