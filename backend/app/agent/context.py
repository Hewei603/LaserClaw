"""Context assembly for case-aware Agent chat."""
from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from ..knowledge.retrieval import results_to_citations, search_case_and_global_knowledge
from ..models import AgentChatMessage, ExperimentCase
from .tools import get_case_payload


def build_chat_context(
    db: Session,
    *,
    case: ExperimentCase | None,
    message: str,
    session_id: int,
    top_k: int = 8,
    history_limit: int = 12,
) -> tuple[dict[str, Any], list[dict[str, Any]], int]:
    """Build the prompt payload for a chat turn."""
    history = (
        db.query(AgentChatMessage)
        .filter(AgentChatMessage.session_id == session_id)
        .order_by(AgentChatMessage.created_at.desc(), AgentChatMessage.id.desc())
        .limit(history_limit)
        .all()
    )
    history_payload = [
        {
            "role": item.role,
            "content": item.content,
            "metadata": item.metadata_json or {},
        }
        for item in reversed(history)
    ]

    run, results = search_case_and_global_knowledge(
        db,
        query=message,
        case_id=case.id if case else None,
        top_k=top_k,
    )
    citations = results_to_citations(results)
    retrieved = [result.model_dump() for result in results]

    context = {
        "message": message,
        "case": get_case_payload(case) if case else None,
        "chat_history": history_payload,
        "retrieved_knowledge": retrieved,
        "citations": citations,
        "instructions": [
            "Answer as a case-aware laser experiment assistant.",
            "Retrieved knowledge is split into two tiers: 'global' (lab-wide SOPs, safety rules, equipment catalogs — treat these as authoritative lab constitution) and 'case' (attachments specific to the linked case — treat these as supplementary experimental data).",
            "Global knowledge takes precedence over case-specific data when they conflict. Always apply lab safety rules and SOPs from global sources.",
            "Use retrieved knowledge when relevant and cite the source title. Say when evidence is missing.",
            "Keep laser operations advisory; do not claim to operate hardware.",
            "If the user asks to generate a plan, troubleshooting guide, report, or ReZonator draft, the backend will call a tool and save an artifact.",
        ],
    }
    return context, citations, run.id
