"""Context assembly for case-aware Agent chat."""
from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from ..knowledge.retrieval import results_to_citations, search_case_and_global_knowledge
from ..models import AgentChatMessage, ExperimentCase
from .memory import get_relevant_memories, get_session_summary
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
    """Build the prompt payload for a chat turn.

    The context includes:
    - recent chat history (up to history_limit messages)
    - a rolling conversation summary (if the session is long)
    - durable memory items extracted from past turns
    - RAG-retrieved knowledge from global and case-specific sources
    """
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

    summary = get_session_summary(db, session_id)
    memories = get_relevant_memories(
        db,
        session_id=session_id,
        case_id=case.id if case else None,
    )

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
        "conversation_summary": summary.summary if summary else None,
        "memories": [
            {
                "memory_type": item.memory_type,
                "content": item.content,
                "importance": item.importance,
            }
            for item in memories
        ],
        "retrieved_knowledge": retrieved,
        "citations": citations,
        "retrieval_confidence": run.confidence,
        "retrieval_no_answer": bool(run.no_answer),
        "retrieval_max_score": round(run.max_score or 0.0, 4),
        "retrieval_message": (run.filters_json or {}).get("low_confidence_message"),
        "instructions": [
            "Answer as a case-aware laser experiment assistant.",
            "Retrieved knowledge is split into two tiers: 'global' (lab-wide SOPs, safety rules, equipment catalogs — treat these as authoritative lab constitution) and 'case' (attachments specific to the linked case — treat these as supplementary experimental data).",
            "Global knowledge takes precedence over case-specific data when they conflict. Always apply lab safety rules and SOPs from global sources.",
            "Use retrieved knowledge when relevant and cite the source title. Say when evidence is missing.",
            "Keep laser operations advisory; do not claim to operate hardware.",
            "If the user asks to generate a plan, troubleshooting guide or report, or to compute a cavity/phase-match/coating/power-curve result, the backend will call a tool and save an artifact.",
            "Use conversation_summary and memories as durable long-term context. Prefer current case data and retrieved knowledge when they conflict with remembered facts.",
        ],
    }
    return context, citations, run.id
