"""A slow pure tool must yield the loop without moving the DB session."""
import asyncio
import threading

import pytest

from app.agent.orchestrator import create_and_run_task
from app.models import AgentToolCall, ExperimentCase


@pytest.mark.asyncio
@pytest.mark.parametrize("mode,tool_name", [("literature_search", "search_literature"),
                                          ("cavity_design", "compute_cavity_design")])
async def test_slow_agent_tool_yields_event_loop_and_saves_trace(db, monkeypatch, mode, tool_name):
    case = ExperimentCase(title="Slow tool", cavity_type="linear", goal="Test")
    db.add(case)
    db.commit()
    event_loop_thread = threading.get_ident()
    started, release = threading.Event(), threading.Event()
    loop = asyncio.get_running_loop()
    worker_started = asyncio.Event()

    def slow_tool(*args):
        assert threading.get_ident() != event_loop_thread
        started.set()
        loop.call_soon_threadsafe(worker_started.set)
        assert release.wait(timeout=3), "event loop did not release the worker"
        return {"status": "completed", "summary": "Test tool finished"}

    target = "run_literature_search" if mode == "literature_search" else "run_physics_tool_payload"
    monkeypatch.setattr(f"app.agent.orchestrator.{target}", slow_tool)
    task = asyncio.create_task(create_and_run_task(db, case_id=case.id, goal="Test", mode=mode))
    try:
        await asyncio.wait_for(worker_started.wait(), timeout=2)
        assert started.is_set() and not task.done()
        # This coroutine can run while the worker is blocked. No timing-based
        # latency threshold is needed to prove the loop is responsive.
        release.set()
        result = await task
    finally:
        release.set()
        if not task.done():
            await task
    assert result.status == "completed" and result.final_content_id
    call = db.query(AgentToolCall).filter_by(task_id=result.id, tool_name=tool_name).one()
    assert call.status == "completed" and call.output_json["status"] == "completed"
