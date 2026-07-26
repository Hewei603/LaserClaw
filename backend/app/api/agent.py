"""Agent task and chat API routes."""
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from ..agent.context import build_chat_context
from ..agent.memory import maybe_summarize_session
from ..agent.orchestrator import create_and_run_task
from ..auth.acl import accessible_case_ids, assert_case_edit, assert_case_view
from ..auth.security import Principal, get_current_principal
from ..database import get_db
from ..models import AgentChatMessage, AgentChatSession, AgentMemoryItem, AgentSessionSummary, AgentTask, AgentToolCall, ExperimentCase
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
    # Chinese - design/compute/select intent for physics + inventory tools
    "帮我设计", "设计一个", "设计", "帮我算", "算一下", "计算", "帮我仿真", "仿真",
    "帮我选", "帮我找", "帮我挑", "选出", "挑选", "筛选",
    "帮我分析", "分析一下", "分析", "拟合", "analyze", "fit",
    # selection verbs fused with their object carry intent by themselves
    "选元件", "找元件", "挑元件", "选镜", "找镜", "选晶体", "找晶体",
    # English
    "generate", "create", "write", "draft", "make", "produce",
    "give me a", "prepare", "build",
    "design", "compute", "calculate", "simulate",
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
    "stability": [
        "稳定性", "功率稳定", "功率计读数", "ocr", "稳定性报告",
        "power stability", "power meter", "stability report",
    ],
    "beam_profile": [
        "光斑", "光斑分析", "光斑直径", "beamgage", "beam profile", "beam spot", "ellipticity",
    ],
    "spectrum": [
        "光谱", "峰值", "中心波长", "谱宽", "半高宽", "fwhm", "spectrum", "wavelength", "linewidth",
    ],
    "components": [
        "器件清单", "元件清单", "采购表", "采购清单", "已有器件",
        "component list", "equipment list", "procurement", "bill of materials", "bom",
    ],
    "module_management": [
        "模块", "添加模块", "更改模块", "删除模块", "case module",
    ],
    "cavity_design": [
        "谐振腔", "腔体设计", "腔设计", "腔长", "稳区", "束腰", "腔内光斑", "摆放位置", "镜距",
        "cavity design", "resonator design", "cavity length", "waist", "stability range", "mirror spacing",
    ],
    "phase_match": [
        "相位匹配", "匹配角", "倍频角", "切角", "走离", "和频角",
        "phase match", "phase-matching", "pm angle", "walk-off", "walkoff", "cut angle",
    ],
    "coating_tmm": [
        "镀膜曲线", "反射率曲线", "膜系", "阻带", "镀膜评估", "镀膜能不能用",
        "coating curve", "reflectivity curve", "stopband", "coating analysis", "tmm",
    ],
    "power_curve": [
        "功率曲线", "输出功率曲线", "阈值", "斜率效率", "泵浦功率",
        "power curve", "slope efficiency", "threshold", "input-output", "p-p curve",
    ],
    "component_match": [
        "选元件", "找元件", "挑元件", "匹配元件", "元件匹配", "库存匹配", "库存里", "现有元件",
        "哪个镜子", "哪块镜子", "哪块晶体", "选镜子", "找镜子",
        "component match", "match components", "which mirror", "from inventory", "in stock",
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

    for mode in ["stability", "beam_profile", "spectrum", "components", "module_management",
                 "cavity_design", "phase_match", "coating_tmm", "component_match", "power_curve",
                 "troubleshooting", "report", "plan"]:
        keywords = _CONTENT_KEYWORDS[mode]
        if any(kw in text for kw in keywords):
            return mode

    return "chat"


def _get_case(case_id: int | None, db: Session, principal: Principal, *, write: bool = False) -> ExperimentCase | None:
    if case_id is None:
        return None
    case = db.query(ExperimentCase).filter(ExperimentCase.id == case_id).first()
    if not case:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Case {case_id} does not exist")
    if write:
        assert_case_edit(db, case, principal)
    else:
        assert_case_view(db, case, principal)
    return case


def _get_or_create_session(request: AgentChatRequest, db: Session, principal: Principal) -> AgentChatSession:
    if request.session_id is not None:
        session = db.query(AgentChatSession).filter(AgentChatSession.id == request.session_id).first()
        if not session:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Agent chat session {request.session_id} does not exist",
            )
        if request.case_id is not None and session.case_id != request.case_id:
            _get_case(request.case_id, db, principal)
            session.case_id = request.case_id
        if session.case_id is not None:
            _get_case(session.case_id, db, principal)
        return session

    case = _get_case(request.case_id, db, principal)
    session = AgentChatSession(case_id=case.id if case else None, title=request.message[:80])
    db.add(session)
    db.flush()
    record_audit(db, action="agent_chat_session.create", resource_type="agent_chat_session", resource_id=str(session.id))
    return session


@router.post("/sessions", response_model=AgentChatSessionResponse, status_code=status.HTTP_201_CREATED)
async def create_chat_session(
    request: AgentChatSessionCreate,
    db: Session = Depends(get_db),
    principal: Principal = Depends(get_current_principal),
):
    """Create a persistent Agent chat session."""
    case = _get_case(request.case_id, db, principal)
    session = AgentChatSession(case_id=case.id if case else None, title=request.title)
    db.add(session)
    db.flush()
    record_audit(db, action="agent_chat_session.create", resource_type="agent_chat_session", resource_id=str(session.id))
    db.commit()
    db.refresh(session)
    return session


@router.get("/sessions", response_model=list[AgentChatSessionResponse])
async def list_chat_sessions(
    case_id: int | None = None,
    db: Session = Depends(get_db),
    principal: Principal = Depends(get_current_principal),
):
    """List Agent chat sessions."""
    query = db.query(AgentChatSession)
    if case_id is not None:
        _get_case(case_id, db, principal)
        query = query.filter(AgentChatSession.case_id == case_id)
    else:
        visible_ids = accessible_case_ids(db, principal)
        if visible_ids is not None:
            query = query.filter((AgentChatSession.case_id.is_(None)) | (AgentChatSession.case_id.in_(visible_ids)))
    return query.order_by(AgentChatSession.created_at.desc()).all()


@router.get("/sessions/{session_id}", response_model=AgentChatSessionResponse)
async def get_chat_session(
    session_id: int,
    db: Session = Depends(get_db),
    principal: Principal = Depends(get_current_principal),
):
    """Get one Agent chat session with messages."""
    session = db.query(AgentChatSession).filter(AgentChatSession.id == session_id).first()
    if not session:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Agent chat session {session_id} does not exist")
    if session.case_id is not None:
        _get_case(session.case_id, db, principal)
    return session


@router.get("/sessions/{session_id}/messages", response_model=list[AgentChatMessageResponse])
async def list_chat_messages(
    session_id: int,
    db: Session = Depends(get_db),
    principal: Principal = Depends(get_current_principal),
):
    """List messages for one Agent chat session."""
    session = db.query(AgentChatSession).filter(AgentChatSession.id == session_id).first()
    if not session:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Agent chat session {session_id} does not exist")
    if session.case_id is not None:
        _get_case(session.case_id, db, principal)
    return session.messages


@router.post("/chat", response_model=AgentChatResponse)
async def chat(
    request: AgentChatRequest,
    db: Session = Depends(get_db),
    principal: Principal = Depends(get_current_principal),
):
    """Chat with LaserClaw Agent, optionally routing the message to a saved tool artifact."""
    session = _get_or_create_session(request, db, principal)
    case = _get_case(session.case_id, db, principal)
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
        await maybe_summarize_session(db, session_id=session.id, case_id=session.case_id)
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
            "report, or physics module result."
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

    assert_case_edit(db, case, principal)
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
    await maybe_summarize_session(db, session_id=session.id, case_id=session.case_id)
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
async def create_task(
    request: AgentTaskCreate,
    db: Session = Depends(get_db),
    principal: Principal = Depends(get_current_principal),
):
    """Create and run an Agent task synchronously."""
    if request.case_id is not None:
        _get_case(request.case_id, db, principal, write=True)
    return await create_and_run_task(
        db,
        case_id=request.case_id,
        goal=request.goal,
        mode=request.mode,
        require_citations=request.require_citations,
    )


@router.get("/tasks", response_model=list[AgentTaskResponse])
async def list_tasks(
    case_id: int | None = None,
    db: Session = Depends(get_db),
    principal: Principal = Depends(get_current_principal),
):
    """List Agent tasks."""
    query = db.query(AgentTask)
    if case_id is not None:
        _get_case(case_id, db, principal)
        query = query.filter(AgentTask.case_id == case_id)
    else:
        visible_ids = accessible_case_ids(db, principal)
        if visible_ids is not None:
            query = query.filter((AgentTask.case_id.is_(None)) | (AgentTask.case_id.in_(visible_ids)))
    return query.order_by(AgentTask.created_at.desc()).all()


@router.get("/tasks/{task_id}", response_model=AgentTaskResponse)
async def get_task(
    task_id: int,
    db: Session = Depends(get_db),
    principal: Principal = Depends(get_current_principal),
):
    """Get one Agent task."""
    task = db.query(AgentTask).filter(AgentTask.id == task_id).first()
    if not task:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Agent task {task_id} does not exist")
    if task.case_id is not None:
        _get_case(task.case_id, db, principal)
    return task


@router.post("/tasks/{task_id}/continue", response_model=AgentTaskResponse)
async def continue_task(
    task_id: int,
    db: Session = Depends(get_db),
    principal: Principal = Depends(get_current_principal),
):
    """Continue a waiting task. Local tasks currently run synchronously, so this returns the existing task."""
    return await get_task(task_id, db, principal)


@router.post("/tasks/{task_id}/cancel", response_model=AgentTaskResponse)
async def cancel_task(
    task_id: int,
    db: Session = Depends(get_db),
    principal: Principal = Depends(get_current_principal),
):
    """Cancel a task that has not completed."""
    task = await get_task(task_id, db, principal)
    if task.case_id is not None:
        _get_case(task.case_id, db, principal, write=True)
    if task.status not in {"completed", "failed", "cancelled"}:
        task.status = "cancelled"
        db.commit()
        db.refresh(task)
    return task


@router.get("/tasks/{task_id}/tool-calls", response_model=list[AgentToolCallResponse])
async def list_task_tool_calls(
    task_id: int,
    db: Session = Depends(get_db),
    principal: Principal = Depends(get_current_principal),
):
    """List tool calls for a task."""
    await get_task(task_id, db, principal)
    return db.query(AgentToolCall).filter(AgentToolCall.task_id == task_id).order_by(AgentToolCall.created_at.asc()).all()


@router.get("/sessions/{session_id}/summary")
async def get_session_summary_api(
    session_id: int,
    db: Session = Depends(get_db),
    principal: Principal = Depends(get_current_principal),
):
    """Return the rolling conversation summary for a session."""
    session = db.query(AgentChatSession).filter(AgentChatSession.id == session_id).first()
    if not session:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Agent chat session {session_id} does not exist")
    if session.case_id is not None:
        _get_case(session.case_id, db, principal)
    summary = (
        db.query(AgentSessionSummary)
        .filter(AgentSessionSummary.session_id == session_id)
        .order_by(
            AgentSessionSummary.updated_at.desc().nullslast(),
            AgentSessionSummary.created_at.desc(),
        )
        .first()
    )
    return {
        "session_id": session_id,
        "summary": summary.summary if summary else None,
        "message_count": summary.message_count if summary else 0,
        "last_message_id": summary.last_message_id if summary else None,
    }


@router.get("/sessions/{session_id}/memories")
async def list_session_memories(
    session_id: int,
    db: Session = Depends(get_db),
    principal: Principal = Depends(get_current_principal),
):
    """Return durable memory items extracted from a session."""
    session = db.query(AgentChatSession).filter(AgentChatSession.id == session_id).first()
    if not session:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Agent chat session {session_id} does not exist")
    if session.case_id is not None:
        _get_case(session.case_id, db, principal)
    items = (
        db.query(AgentMemoryItem)
        .filter(AgentMemoryItem.session_id == session_id)
        .order_by(AgentMemoryItem.importance.desc(), AgentMemoryItem.created_at.desc())
        .all()
    )
    return [
        {
            "id": item.id,
            "memory_type": item.memory_type,
            "content": item.content,
            "importance": item.importance,
            "created_at": item.created_at,
        }
        for item in items
    ]
