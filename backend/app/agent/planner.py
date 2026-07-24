"""Simple deterministic Agent planner."""
from __future__ import annotations


def build_plan(mode: str) -> list[dict[str, str]]:
    """Return a minimal multi-step plan for the requested Agent mode."""
    if mode in {"stability", "beam_profile", "spectrum", "components", "module_management",
                "cavity_design", "phase_match", "coating_tmm", "component_match"}:
        return [
            {
                "title": "Read case and module context",
                "rationale": "The Agent must understand the current case and existing optional modules.",
            },
            {
                "title": "Inspect module inputs",
                "rationale": "Module workflows depend on uploaded files, parameters, and prior generated artifacts.",
            },
            {
                "title": f"Run {mode} module workflow",
                "rationale": "Create or update the requested case module through auditable tools.",
            },
            {
                "title": "Save module result and audit trail",
                "rationale": "Persist module outputs, generated content, and tool calls for review.",
            },
        ]
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
