"""Rolling summary and durable memory service for Agent chat sessions.

The summary lifecycle:
1. Every chat turn, maybe_summarize_session() checks whether the session has
   accumulated enough new messages since the last summary.
2. If yes, the oldest unsummarised messages (all but the most recent
   RECENT_MESSAGES_TO_KEEP) are sent to the provider's summarize_chat().
3. The returned summary text overwrites the existing AgentSessionSummary row
   (one row per session); extracted memory items are appended to
   agent_memory_items.
4. build_chat_context() reads both tables and injects them into the prompt.
"""
from __future__ import annotations

from sqlalchemy.orm import Session

from ..models import AgentChatMessage, AgentMemoryItem, AgentSessionSummary
from ..providers import get_ai_provider


SUMMARY_TRIGGER_MESSAGES = 16
RECENT_MESSAGES_TO_KEEP = 6


def get_session_summary(db: Session, session_id: int) -> AgentSessionSummary | None:
    return (
        db.query(AgentSessionSummary)
        .filter(AgentSessionSummary.session_id == session_id)
        .order_by(
            AgentSessionSummary.updated_at.desc().nullslast(),
            AgentSessionSummary.created_at.desc(),
        )
        .first()
    )


def get_relevant_memories(
    db: Session,
    *,
    session_id: int,
    case_id: int | None,
    limit: int = 8,
) -> list[AgentMemoryItem]:
    """Return the most important memories for this session/case pair."""
    query = db.query(AgentMemoryItem)
    if case_id is not None:
        query = query.filter(
            (AgentMemoryItem.case_id == case_id) | (AgentMemoryItem.session_id == session_id)
        )
    else:
        query = query.filter(AgentMemoryItem.session_id == session_id)
    return (
        query
        .order_by(AgentMemoryItem.importance.desc(), AgentMemoryItem.created_at.desc())
        .limit(limit)
        .all()
    )


async def maybe_summarize_session(
    db: Session,
    *,
    session_id: int,
    case_id: int | None = None,
    user_id: int | None = None,
) -> None:
    """Compress old messages into a rolling summary when the session is long enough.

    Idempotent: if there are not enough new messages since the last summary,
    this is a no-op. The most recent RECENT_MESSAGES_TO_KEEP messages are
    never compressed so the immediate context is always available verbatim.
    """
    messages = (
        db.query(AgentChatMessage)
        .filter(AgentChatMessage.session_id == session_id)
        .order_by(AgentChatMessage.created_at.asc(), AgentChatMessage.id.asc())
        .all()
    )
    if len(messages) < SUMMARY_TRIGGER_MESSAGES:
        return

    existing = get_session_summary(db, session_id)
    last_summarised_id = existing.last_message_id if existing else None

    # Only messages after the last summarised one are candidates
    candidates = [m for m in messages if last_summarised_id is None or m.id > last_summarised_id]
    min_new = SUMMARY_TRIGGER_MESSAGES - RECENT_MESSAGES_TO_KEEP
    if len(candidates) < min_new:
        return

    # Leave the most recent messages untouched
    to_summarise = candidates[:-RECENT_MESSAGES_TO_KEEP]
    if not to_summarise:
        return

    payload = [{"role": m.role, "content": m.content} for m in to_summarise]
    result = await get_ai_provider().summarize_chat(
        payload,
        previous_summary=existing.summary if existing else None,
    )

    if existing is None:
        existing = AgentSessionSummary(
            session_id=session_id,
            summary=result["summary"],
            metadata_json={"strategy": "rolling_summary_v1"},
        )
        db.add(existing)
    existing.summary = result["summary"]
    existing.message_count = len(messages)
    existing.last_message_id = to_summarise[-1].id
    existing.metadata_json = {"strategy": "rolling_summary_v1"}

    for item in result.get("memories", []):
        content = item.get("content")
        if not content:
            continue
        db.add(
            AgentMemoryItem(
                session_id=session_id,
                case_id=case_id,
                user_id=user_id,
                memory_type=item.get("memory_type", "fact"),
                content=content,
                importance=int(item.get("importance", 1)),
                source_message_id=to_summarise[-1].id,
                metadata_json={"source": "summarize_chat"},
            )
        )
