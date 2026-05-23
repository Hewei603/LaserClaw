"""Agent task and chat API routes."""
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from ..agent.context import build_chat_context
from ..agent.orchestrator import create_and_run_task
from ..agent.tools import tool_schemas
from ..database import get_db
from ..models import AgentChatMessage, AgentChatSession, AgentTask, AgentToolCall, ExperimentCase
from ..observability.audit import record_audit
from ..providers import get_ai_provider
from ..schemas import (
    AgentChatMessageResponse,
    AgentChatRequest,
    AgentChatResponse,
    AgentChatSessionCreate,
    AgentChatSessionResponse,
    AgentTaskCreate,
    AgentTaskResponse,
    AgentToolCallResponse,
)

router = APIRouter()

# ---------------------------------------------------------------------------
# Generation intent keywords — user must express intent to CREATE something
# ---------------------------------------------------------------------------
_GENERATE_INTENT = [
    # Chinese
    "生成", "帮我写", "帮我做", "帮我生成", "帮我制定", "帮我草拟",
    "给我写", "给我生成", "给我做", "写一个", "写一份", "制定",
    "草拟", "出一份", "出一个", "整理", "总结一下", "做一个", "做一份",
    # English
    "generate", "create", "write", "draft", "make", "produce",
    "give me a", "prepare", "build",
]

# Content type keywords — what to generate
_CONTENT_KEYWORDS = {
    "plan": [
        "实验计划", "实验方案", "实验步骤", "操作步骤", "搭建方案", "实验流程",
        "plan", "protocol", "procedure", "experiment plan", "setup guide",
    ],
    "troubleshooting": [
        "故障排查", "排查方案", "排查指南", "排查报告",
        "troubleshooting", "troubleshoot guide", "fault analysis", "diagnostic",
    ],
    "report": [
        "实验报告", "报告", "总结报告", "实验总结",
        "report", "experiment report", "lab report", "summary report",
    ],
    "rezonator": [
        "rezonator", "仿真输入", "腔型草稿", "谐振腔草稿", "腔参数草稿",
        "resonator draft", "simulation input", "cavity draft",
    ],
}


def _route_mode(message: str) -> str:
    """Detect generation intent + content type from user message.

    Requires BOTH an intent keyword and a content-type keyword to route
    to a generation tool. Falls back to 'chat' if intent is ambiguous.
    """
    text = message.lower()

    has_intent = any(kw in text for kw in _GENERATE_INTENT)
    if not has_intent:
        return "chat"

    for mode in ["rezonator", "troubleshooting", "report", "plan"]:
        keywords = _CONTENT_KEYWORDS[mode]
        if any(kw in text for kw in keywords):
            return mode

    return "chat"


def _get_case(case_id: int | None, db: Session) -> ExperimentCase | None:
    if case_id is None:
        return None
    case = db.query(ExperimentCase).filter(ExperimentCase.id == case_id).first()
    if not case:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Case {case_id} does not exist")
    return case


def _get_or_create_session(request: AgentChatRequest, db: Session) -> AgentChatSession:
    if request.session_id is not None:
        session = db.query(AgentChatSession).filter(AgentChatSession.id == request.session_id).first()
        if not session:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Agent chat session {request.session_id} does not exist",
            )
        if request.case_id is not None and session.case_id != request.case_id:
            _get_case(request.case_id, db)
            session.case_id = request.case_id
        return session

    case = _get_case(request.case_id, db)
    session = AgentChatSession(case_id=case.id if case else None, title=request.message[:80])
    db.add(session)
    db.flush()
    record_audit(db, action="agent_chat_session.create", resource_type="agent_chat_session", resource_id=str(session.id))
    return session


@router.post("/sessions", response_model=AgentChatSessionResponse, status_code=status.HTTP_201_CREATED)
async def create_chat_session(request: AgentChatSessionCreate, db: Session = Depends(get_db)):
    """Create a persistent Agent chat session."""
    case = _get_case(request.case_id, db)
    session = AgentChatSession(case_id=case.id if case else None, title=request.title)
    db.add(session)
    db.flush()
    record_audit(db, action="agent_chat_session.create", resource_type="agent_chat_session", resource_id=str(session.id))
    db.commit()
    db.refresh(session)
    return session


@router.get("/sessions", response_model=list[AgentChatSessionResponse])
async def list_chat_sessions(case_id: int | None = None, db: Session = Depends(get_db)):
    """List Agent chat sessions."""
    query = db.query(AgentChatSession)
    if case_id is not None:
        query = query.filter(AgentChatSession.case_id == case_id)
    return query.order_by(AgentChatSession.created_at.desc()).all()


@router.get("/sessions/{session_id}", response_model=AgentChatSessionResponse)
async def get_chat_session(session_id: int, db: Session = Depends(get_db)):
    """Get one Agent chat session with messages."""
    session = db.query(AgentChatSession).filter(AgentChatSession.id == session_id).first()
    if not session:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Agent chat session {session_id} does not exist")
    return session


@router.get("/sessions/{session_id}/messages", response_model=list[AgentChatMessageResponse])
async def list_chat_messages(session_id: int, db: Session = Depends(get_db)):
    """List messages for one Agent chat session."""
    session = db.query(AgentChatSession).filter(AgentChatSession.id == session_id).first()
    if not session:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Agent chat session {session_id} does not exist")
    return session.messages


@router.post("/chat", response_model=AgentChatResponse)
async def chat(request: AgentChatRequest, db: Session = Depends(get_db)):
    """Chat with LaserClaw Agent, optionally routing the message to a saved tool artifact."""
    session = _get_or_create_session(request, db)
    case = _get_case(session.case_id, db)
    db.add(AgentChatMessage(session_id=session.id, role="user", content=request.message, metadata_json={"mode": request.mode}))
    db.flush()

    routed_mode = request.mode if request.mode != "auto" else _route_mode(request.message)
    context, citations, retrieval_run_id = build_chat_context(
        db,
        case=case,
        message=request.message,
        session_id=session.id,
    )

    if routed_mode == "chat":
        content = await get_ai_provider().generate_chat_response(context)
        assistant_text = content.get("message") or "I reviewed the available case context and knowledge sources."
        db.add(
            AgentChatMessage(
                session_id=session.id,
                role="assistant",
                content=assistant_text,
                metadata_json={
                    "routed_mode": routed_mode,
                    "citations": citations,
                    "retrieval_run_id": retrieval_run_id,
                    "provider_content": content,
                },
            )
        )
        record_audit(db, action="agent_chat.message", resource_type="agent_chat_session", resource_id=str(session.id))
        db.commit()
        return AgentChatResponse(
            session_id=session.id,
            message=assistant_text,
            routed_mode="chat",
            task=None,
            citations=citations,
        )

    if case is None:
        assistant_text = (
            "Link a case before asking LaserClaw to create a saved plan, troubleshooting guide, "
            "report, or ReZonator draft."
        )
        db.add(
            AgentChatMessage(
                session_id=session.id,
                role="assistant",
                content=assistant_text,
                metadata_json={"routed_mode": "chat", "reason": "missing_case"},
            )
        )
        db.commit()
        return AgentChatResponse(
            session_id=session.id,
            message=assistant_text,
            routed_mode="chat",
            task=None,
            citations=citations,
        )

    task = await create_and_run_task(
        db,
        case_id=case.id,
        goal=request.message,
        mode=routed_mode,
        require_citations=request.require_citations,
        extra_context=context,
    )
    assistant_text = f"Created and completed a {routed_mode} artifact. It is saved on the linked case."
    db.add(
        AgentChatMessage(
            session_id=session.id,
            role="assistant",
            content=assistant_text,
            metadata_json={
                "routed_mode": routed_mode,
                "task_id": task.id,
                "generated_content_id": task.final_content_id,
                "citations": citations,
                "retrieval_run_id": retrieval_run_id,
            },
        )
    )
    db.commit()
    return AgentChatResponse(
        session_id=session.id,
        message=assistant_text,
        routed_mode=routed_mode,
        task=task,
        generated_content_id=task.final_content_id,
        citations=citations,
    )


@router.post("/tasks", response_model=AgentTaskResponse, status_code=status.HTTP_201_CREATED)
async def create_task(request: AgentTaskCreate, db: Session = Depends(get_db)):
    """Create and run an Agent task synchronously."""
    if request.case_id is not None:
        _get_case(request.case_id, db)
    return await create_and_run_task(
        db,
        case_id=request.case_id,
        goal=request.goal,
        mode=request.mode,
        require_citations=request.require_citations,
    )


@router.get("/tasks", response_model=list[AgentTaskResponse])
async def list_tasks(case_id: int | None = None, db: Session = Depends(get_db)):
    """List Agent tasks."""
    query = db.query(AgentTask)
    if case_id is not None:
        query = query.filter(AgentTask.case_id == case_id)
    return query.order_by(AgentTask.created_at.desc()).all()


@router.get("/tasks/{task_id}", response_model=AgentTaskResponse)
async def get_task(task_id: int, db: Session = Depends(get_db)):
    """Get one Agent task."""
    task = db.query(AgentTask).filter(AgentTask.id == task_id).first()
    if not task:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Agent task {task_id} does not exist")
    return task


@router.post("/tasks/{task_id}/continue", response_model=AgentTaskResponse)
async def continue_task(task_id: int, db: Session = Depends(get_db)):
    """Continue a waiting task. Local tasks currently run synchronously, so this returns the existing task."""
    return await get_task(task_id, db)


@router.post("/tasks/{task_id}/cancel", response_model=AgentTaskResponse)
async def cancel_task(task_id: int, db: Session = Depends(get_db)):
    """Cancel a task that has not completed."""
    task = await get_task(task_id, db)
    if task.status not in {"completed", "failed", "cancelled"}:
        task.status = "cancelled"
        db.commit()
        db.refresh(task)
    return task


@router.get("/tasks/{task_id}/tool-calls", response_model=list[AgentToolCallResponse])
async def list_task_tool_calls(task_id: int, db: Session = Depends(get_db)):
    """List tool calls for a task."""
    return db.query(AgentToolCall).filter(AgentToolCall.task_id == task_id).order_by(AgentToolCall.created_at.asc()).all()
