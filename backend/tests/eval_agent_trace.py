"""Agent trace completeness evaluation — 20+ test runs.

Run with: pytest backend/tests/eval_agent_trace.py -v -s
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.main import app
from app.database import get_db
from app.models import AgentTask, AgentStep, AgentToolCall, GeneratedContent

client = TestClient(app)

# ---------------------------------------------------------------------------
# Fixtures (reuse conftest db setup)
# ---------------------------------------------------------------------------
TRACE_TEST_GOALS = [
    ("plan", "帮我制定一个 Nd:YAG 激光器实验计划"),
    ("troubleshooting", "激光功率低，不出光，怎么排查"),
    ("report", "生成本次 Nd:YAG 实验报告"),
    ("plan", "如何搭建倍频 532nm 系统"),
    ("troubleshooting", "光斑异常，模式跳变，如何处理"),
    ("report", "总结这次激光准直实验"),
    ("plan", "Nd:YAG Q-switched 实验步骤"),
    ("troubleshooting", "LBO 倍频输出功率波动，排查"),
]


# ---------------------------------------------------------------------------
# Trace field checkers
# ---------------------------------------------------------------------------
def check_trace_completeness(task: AgentTask, db: Session) -> dict:
    """Check all required trace fields for an AgentTask."""
    checks = {
        "task_status_present": task.status in ("completed", "failed"),
        "task_goal_present": bool(task.goal),
        "task_mode_present": bool(task.mode),
        "steps_present": False,
        "tool_calls_present": False,
        "artifact_present": False,
        "error_state_present": task.status in ("completed", "failed"),
    }

    steps = db.query(AgentStep).filter(AgentStep.task_id == task.id).all()
    checks["steps_present"] = len(steps) >= 4

    tool_calls = db.query(AgentToolCall).filter(AgentToolCall.task_id == task.id).all()
    checks["tool_calls_present"] = len(tool_calls) >= 1

    if task.status == "completed":
        artifact = db.query(GeneratedContent).filter(GeneratedContent.id == task.final_content_id).first()
        checks["artifact_present"] = artifact is not None

    completeness_score = sum(checks.values()) / len(checks)
    return {
        "task_id": task.id,
        "task_mode": task.mode,
        "task_status": task.status,
        "checks": checks,
        "completeness_score": completeness_score,
        "steps_count": len(steps),
        "tool_calls_count": len(tool_calls),
    }


# ---------------------------------------------------------------------------
# Individual pytest tests (use db fixture from conftest)
# ---------------------------------------------------------------------------
@pytest.fixture
def case_id(client_with_db):
    """Create a test case and return its ID."""
    tc, db = client_with_db
    resp = tc.post("/api/cases", json={
        "title": "Trace Eval Test Case",
        "description": "Nd:YAG CW laser for trace evaluation",
        "cavity_type": "linear",
        "goal": "Evaluate agent trace completeness",
        "parameters": {"wavelength_nm": 1064},
        "symptoms": [],
    })
    assert resp.status_code == 201
    return resp.json()["id"]


@pytest.fixture
def client_with_db(db):
    """Return (TestClient, session) tuple.

    The session fixture in conftest is named ``db``; this file asked for a
    non-existent ``db_session``, so every test here errored out on collection
    and the trace-completeness metric it produces had no working producer.
    """
    def override_get_db():
        try:
            yield db
        finally:
            pass

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as tc:
        yield tc, db
    app.dependency_overrides.clear()


def _run_agent_task(tc: TestClient, case_id: int, mode: str, goal: str) -> dict:
    """Helper to run an agent task and return the response JSON."""
    resp = tc.post("/api/agent/tasks", json={
        "case_id": case_id,
        "goal": goal,
        "mode": mode,
    })
    return resp.json(), resp.status_code


@pytest.mark.parametrize("mode,goal", TRACE_TEST_GOALS[:5])
def test_agent_trace_fields_present(client_with_db, mode, goal):
    """Verify trace fields are persisted for agent tasks."""
    tc, db = client_with_db

    # Create case
    resp = tc.post("/api/cases", json={
        "title": f"Trace Test {mode}",
        "description": "Test case for trace evaluation",
        "cavity_type": "linear",
        "goal": goal,
        "parameters": {},
        "symptoms": ["功率低"] if mode == "troubleshooting" else [],
    })
    assert resp.status_code == 201
    cid = resp.json()["id"]

    # Run agent task
    task_resp, status_code = _run_agent_task(tc, cid, mode, goal)
    assert status_code in (200, 201), f"Task failed: {task_resp}"

    task_id = task_resp.get("id")
    assert task_id is not None

    # Fetch task from DB and check trace
    task = db.query(AgentTask).filter(AgentTask.id == task_id).first()
    assert task is not None
    assert task.status == "completed"
    assert task.goal == goal
    assert task.mode == mode

    steps = db.query(AgentStep).filter(AgentStep.task_id == task_id).all()
    assert len(steps) >= 4, f"Expected >= 4 steps, got {len(steps)}"

    tool_calls = db.query(AgentToolCall).filter(AgentToolCall.task_id == task_id).all()
    assert len(tool_calls) >= 1, "Expected at least 1 tool call"

    artifact = db.query(GeneratedContent).filter(GeneratedContent.id == task.final_content_id).first()
    assert artifact is not None, "Expected artifact to be saved"
    assert artifact.content_type == (mode if mode != "plan" else "plan")


def test_agent_trace_step_statuses(client_with_db):
    """All steps should be completed after successful task."""
    tc, db = client_with_db

    resp = tc.post("/api/cases", json={
        "title": "Step Status Test",
        "description": "Test step status tracking",
        "cavity_type": "linear",
        "goal": "Generate plan",
        "parameters": {},
        "symptoms": [],
    })
    cid = resp.json()["id"]

    task_resp, _ = _run_agent_task(tc, cid, "plan", "制定实验计划")
    task_id = task_resp.get("id")

    steps = db.query(AgentStep).filter(AgentStep.task_id == task_id).order_by(AgentStep.step_index).all()
    for step in steps:
        assert step.status == "completed", f"Step {step.step_index} has status {step.status}"
        assert step.result_summary, f"Step {step.step_index} missing result_summary"


def test_agent_trace_tool_call_latency_recorded(client_with_db):
    """Tool calls should have latency_ms recorded."""
    tc, db = client_with_db

    resp = tc.post("/api/cases", json={
        "title": "Latency Test",
        "description": "Test tool call latency recording",
        "cavity_type": "linear",
        "goal": "Test latency",
        "parameters": {},
        "symptoms": [],
    })
    cid = resp.json()["id"]

    task_resp, _ = _run_agent_task(tc, cid, "plan", "实验计划")
    task_id = task_resp.get("id")

    tool_calls = db.query(AgentToolCall).filter(AgentToolCall.task_id == task_id).all()
    for tc_record in tool_calls:
        assert tc_record.latency_ms is not None
        assert tc_record.latency_ms >= 0
