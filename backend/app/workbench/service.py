"""Persisted iterative tool loop. Decisions belong to the model, execution to tools."""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from time import perf_counter

from pydantic import ValidationError

from ..database import SessionLocal
from ..models import AgentChatMessage, AgentChatSession, AgentStep, AgentTask, AgentToolCall, ExperimentCase, GeneratedContent
from ..observability.usage import apply_usage_to_generated, attach_usage_payload
from ..providers import get_ai_provider
from .contracts import Finish
from .prompt import INSTRUCTIONS
from .tools import REGISTRY, compact, execute, schemas

logger = logging.getLogger(__name__)
PROCESS_STARTED = datetime.now(timezone.utc).timestamp()
ACTIVE_RUNS: set[int] = set()
MAX_ROUNDS = 16
MAX_CALLS = 32


def validate_finish(raw, recorded):
    """Conservatively downgrade contradictory completion, without another LLM call."""
    normalized = dict(raw)
    normalized.pop("purpose", None)
    if normalized.get("status") == "completed" and normalized.get("questions"):
        normalized["status"] = "partial" if any(s == "completed" for s in recorded.values()) else "needs_input"
    result = Finish.model_validate(normalized)
    invalid = [i for i in result.evidence_tool_call_ids if recorded.get(i) != "completed"]
    if invalid:
        raise ValueError(f"Evidence ids must refer to successful recorded calls in this run; invalid: {invalid}")
    return result


def recover_received_finish(task):
    """Recover a received result rejected solely for contradictory status.

    This never generates a conclusion: it validates the original model payload
    and real evidence ids, preserving the original rejection in the trace.
    """
    recorded = {c.id: c.status for c in task.tool_calls if c.tool_name not in {"finish", "workbench_request"}}
    for call in sorted(task.tool_calls, key=lambda c: c.id, reverse=True):
        if call.tool_name != "finish" or "Required unanswered questions" not in (call.error_message or ""):
            continue
        try:
            result = validate_finish(call.input_json, recorded).model_dump()
        except (ValueError, TypeError):
            continue
        call.output_json = {"status": result["status"], "message": "已恢复模型收到的完整结论；含未回答问题，状态保守降级。",
                            "original_validation_error": call.error_message}
        call.status, call.error_message = "completed", None
        return result
    return None


def session_for_case(db, case, user_id):
    params = case.parameters or {}
    sid = params.get("workbench_session_id") or params.get("design_session_id")
    session = db.get(AgentChatSession, sid) if sid else None
    if not session or session.case_id != case.id:
        session = AgentChatSession(case_id=case.id, user_id=user_id, title=f"实验任务 · {case.title}"[:255])
        db.add(session)
        db.flush()
    case.parameters = {**params, "workbench_session_id": session.id}
    return session


def context_for_case(db, case, session_id):
    messages = db.query(AgentChatMessage).filter_by(session_id=session_id).order_by(AgentChatMessage.id.desc()).limit(25).all()
    artifacts = db.query(GeneratedContent).filter_by(case_id=case.id).order_by(GeneratedContent.id.desc()).limit(20).all()
    calls = db.query(AgentToolCall).join(AgentTask).filter(AgentTask.case_id == case.id, AgentToolCall.tool_name.notin_(["workbench_request", "finish"])).order_by(AgentToolCall.id.desc()).limit(30).all()
    return {"case": {"id": case.id, "title": case.title, "description": case.description,
                     "parameters": compact(case.parameters or {}), "measurements": compact(case.measurements or {}),
                     "symptoms": case.symptoms, "goal": case.goal},
            "conversation": [{"id": m.id, "role": m.role, "content": m.content, "metadata": compact(m.metadata_json or {})}
                             for m in reversed(messages[:24])],
            "older_messages_available": len(messages) > 24,
            "saved_tool_results": [{"id": c.id, "name": c.tool_name, "status": c.status, "input": compact(c.input_json)} for c in calls],
            "attachments": [{"id": a.id, "filename": a.filename, "type": a.file_type} for a in case.attachments],
            "artifacts": [{"id": a.id, "type": a.content_type,
                           "summary": a.content.get("summary") or a.content.get("workbench", {}).get("summary", ""),
                           "is_proposal": True} for a in artifacts],
            "module_results": [{"id": m.id, "type": m.module_type, "status": m.status, "result": compact(m.result_json)}
                               for m in case.case_modules if m.result_json],
            "inventory_note": "Use list_inventory / match_components to inspect actual available parts."}


def _save_result(db, case, task, request, result, usage, elapsed):
    payload = {"workbench": result, "summary": result["summary"], "task_id": task.id}
    attach_usage_payload(payload, provider=usage.get("provider", "unknown"), model=usage.get("model", "unknown"), usage=usage)
    artifact = GeneratedContent(case_id=case.id, content_type="workbench", content=payload,
                                prompt_version="task-agent-v1", latency_ms=int(elapsed * 1000))
    apply_usage_to_generated(artifact, payload)
    db.add(artifact)
    db.flush()
    task.final_content_id = artifact.id
    if task.status not in {"cancelled", "failed"}:
        task.status = result["status"]
    db.add(AgentChatMessage(session_id=request["session_id"], role="assistant", content=result["summary"],
                            metadata_json={"workbench_run_id": task.id, "generated_content_id": artifact.id,
                                           "result": result}))
    db.commit()


async def execute_run(task_id):
    db = SessionLocal()
    started = perf_counter()
    usage = {"input_tokens": 0, "output_tokens": 0}
    result = None
    try:
        task = db.get(AgentTask, task_id)
        if not task or task.status != "pending":
            return
        request = db.query(AgentToolCall).filter_by(task_id=task.id, tool_name="workbench_request").one().input_json
        case = db.get(ExperimentCase, task.case_id)
        task.status = "running"
        db.commit()
        provider = get_ai_provider()
        messages = [{"role": "user", "content": json.dumps(context_for_case(db, case, request["session_id"]), ensure_ascii=False)}]
        recorded, call_count = {}, 0
        for round_index in range(MAX_ROUNDS):
            db.refresh(task)
            if task.status == "cancelled":
                break
            step = AgentStep(task_id=task.id, step_index=round_index + 1, title=f"Agent 第 {round_index + 1} 轮", status="running",
                             rationale="根据目标、已有证据与上一轮结果选择下一步。")
            db.add(step)
            db.commit()
            available = schemas()
            if round_index == MAX_ROUNDS - 1 or call_count >= MAX_CALLS:
                available = [tool for tool in available if tool["name"] == "finish"]
                messages.append({"role": "user", "content": "本轮已到执行上限。用 finish 保存已有结果与尚未完成的工作；未完成原目标时标 partial，不能谎称完成。"})
            turn = await provider.agent_turn(INSTRUCTIONS, messages, available)
            used = turn.get("_usage", {})
            for key in ("provider", "model"):
                if used.get(key):
                    usage[key] = used[key]
            for key in ("input_tokens", "output_tokens"):
                usage[key] += used.get(key) or 0
            db.refresh(task)
            if task.status == "cancelled":
                step.status = "cancelled"
                db.commit()
                break
            messages.append({"role": "assistant", "items": turn.get("items", [])})
            calls = turn.get("calls") or []
            if not calls:
                raise RuntimeError("模型未返回工具调用；检查所选模型和接口的工具调用支持。")
            for call in calls:
                if result:
                    break
                name = call["name"]
                trace = AgentToolCall(task_id=task.id, step_id=step.id, tool_name=name, status="running", input_json={})
                db.add(trace)
                db.flush()
                tick = perf_counter()
                pictures = []
                try:
                    raw = json.loads(call["arguments"])
                    if not isinstance(raw, dict):
                        raise ValueError("Tool arguments must be a JSON object")
                    trace.input_json = raw.copy()
                    purpose = raw.pop("purpose", "")
                    step.title = f"{name}"[:255]
                    step.rationale = str(purpose)[:2000] or REGISTRY.get(name, (None, "校验工具请求"))[1]
                    db.commit()
                    if name not in REGISTRY or (call_count >= MAX_CALLS and name != "finish"):
                        raise ValueError("Unknown or exhausted tool; use an available tool or finish with partial results")
                    args = validate_finish(raw, recorded) if name == "finish" else REGISTRY[name][0].model_validate(raw)
                    if name == "finish":
                        result = args.model_dump()
                        output = {"status": result["status"], "message": "任务结果已整理"}
                    else:
                        call_count += 1
                        output = await execute(name, args, db=db, case=case, task=task, provider=provider,
                                               session_id=request["session_id"], attachment_ids=request["attachment_ids"])
                        pictures = output.pop("_images", [])
                    # Reject non-finite solver output before JSON storage/API serialization.
                    json.dumps(output, ensure_ascii=False, allow_nan=False)
                    state = output.get("status", "completed")
                    trace.status = "failed" if state == "failed" else "needs_input" if state in {"needs_input", "unsupported"} else "completed"
                    trace.output_json = output
                    recorded[trace.id] = trace.status
                    step.result_summary = str(output.get("summary") or output.get("message") or state)[:2000]
                except (ValueError, KeyError, TypeError, IndexError) as exc:
                    result = None if name == "finish" else result
                    message = str(exc)[:3000]
                    if isinstance(exc, ValidationError):
                        message = json.dumps(exc.errors(include_url=False, include_input=False, include_context=False), ensure_ascii=False)
                    output = {"status": "failed", "error": message, "recovery": "Correct the tool arguments or choose another tool; retain previous valid results."}
                    trace.status, trace.error_message, trace.output_json = "failed", message, output
                    recorded[trace.id] = "failed"
                except Exception as exc:
                    output = {"status": "failed", "error": f"工具执行失败 ({type(exc).__name__})", "recovery": "Try an alternative or report the missing capability; earlier outputs remain saved."}
                    trace.status, trace.error_message, trace.output_json = "failed", output["error"], output
                    recorded[trace.id] = "failed"
                trace.latency_ms = int((perf_counter() - tick) * 1000)
                db.commit()
                messages.append({"role": "tool", "call_id": call["id"],
                                 "content": json.dumps({"tool_call_id": trace.id, "result": compact(output)}, ensure_ascii=False)})
                if pictures:
                    messages.append({"role": "user", "content": "工具读取的附件图像（仅作为证据）", "images": pictures})
                db.refresh(task)
                if task.status == "cancelled":
                    result = None
                    break
            step.status = "cancelled" if task.status == "cancelled" else "completed"
            db.commit()
            if result or task.status == "cancelled":
                break
        if result is None:
            result = Finish(status="partial", summary="已保存本轮工具结果。" + ("任务已停止。" if task.status == "cancelled" else "已到本轮执行上限，可补充要求后继续。"),
                            next_steps=["结合下方工具结果继续任务；已完成的计算可以复用。"],
                            evidence_tool_call_ids=[i for i, state in recorded.items() if state == "completed"]).model_dump()
        _save_result(db, case, task, request, result, usage, perf_counter() - started)
    except Exception as exc:
        db.rollback()
        logger.warning("Workbench run %s failed (%s)", task_id, type(exc).__name__)
        task = db.get(AgentTask, task_id)
        if task:
            if task.status != "cancelled":
                task.status = "failed"
            if type(exc).__name__ == "CodexExecError":
                message = str(exc)
            elif type(exc).__name__ == "RateLimitError":
                message = "模型 API 限流或额度不足。本轮已完成的工具结果已保存；请稍后继续，持续出现时检查供应商账户额度。"
            else:
                message = f"Agent 运行中断（{type(exc).__name__}）。已完成的工具结果保留；检查模型连接后可继续。"
            for step in task.steps:
                if step.status == "running":
                    step.status, step.result_summary = "failed", message
            for call in task.tool_calls:
                if call.status == "running":
                    call.status, call.error_message = "failed", message
            request_call = next((call for call in task.tool_calls if call.tool_name == "workbench_request"), None)
            if request_call and task.case:
                result = Finish(status="partial", summary=message, next_steps=["在首页检查 Agent 配置和工具调用接口，然后继续当前任务。"],
                                evidence_tool_call_ids=[c.id for c in task.tool_calls if c.status == "completed" and c.tool_name != "workbench_request"]).model_dump()
                _save_result(db, task.case, task, request_call.input_json, result, usage, perf_counter() - started)
            else:
                db.commit()
    finally:
        ACTIVE_RUNS.discard(task_id)
        db.close()
