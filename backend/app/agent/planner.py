"""Simple deterministic Agent planner."""
from __future__ import annotations


def build_plan(mode: str) -> list[dict[str, str]]:
    """Return a minimal multi-step plan for the requested Agent mode."""
    return [
        {
            "title": "Read case context",
            "rationale": "The Agent must ground its work in the selected experiment case.",
        },
        {
            "title": "Retrieve related knowledge",
            "rationale": "Historical cases, attachments, and generated artifacts provide evidence.",
        },
        {
            "title": f"Create {mode} draft",
            "rationale": "Use the case and retrieved evidence to produce a structured artifact.",
        },
        {
            "title": "Save artifact and audit trail",
            "rationale": "Persist output, steps, and tool calls for review.",
        },
    ]
