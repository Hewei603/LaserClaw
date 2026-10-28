"""Recalculate an existing linear design from quoted facts without calling an LLM.

Dry-run by default. --write appends a clearly identified direct-kernel run,
design and editable project. Existing facts and all earlier artifacts survive.
Evidence JSON: {sources: {message: "literal user text"}, facts: [...] }.
This is an explicit operator path, never an automatic substitute for an Agent.
"""
import argparse
import asyncio
import json
import sys
from pathlib import Path
from time import perf_counter

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.database import SessionLocal  # noqa: E402
from app.design.brief import merge_facts  # noqa: E402
from app.design.rezonator import cold_cavity_schema  # noqa: E402
from app.design.service import inventory_snapshot  # noqa: E402
from app.design.solver import solve_design  # noqa: E402
from app.models import AgentChatMessage, AgentTask, AgentToolCall, ExperimentCase, GeneratedContent  # noqa: E402
from app.workbench.projects import read_project  # noqa: E402
from app.workbench.service import session_for_case  # noqa: E402
from app.workbench.tools import REGISTRY, execute  # noqa: E402


async def run(args):
    evidence = json.loads(Path(args.evidence).read_text(encoding="utf-8"))
    with SessionLocal() as db:
        case = db.get(ExperimentCase, args.case_id)
        if case is None:
            raise ValueError("Case does not exist")
        facts, changes, notes = merge_facts((case.parameters or {}).get("design_facts", {}), evidence, evidence["sources"], [])
        if notes:
            raise ValueError(f"Unaccepted evidence: {notes}")
        started = perf_counter()
        design = solve_design(facts, inventory_snapshot(db))
        design.update(changes=changes, intake_notes=["操作员依据用户原话更新事实，直接调用确定性内核；本次未调用 LLM。"])
        if not design.get("candidates"):
            raise ValueError(f"No candidate: {design.get('issues')}")
        candidate = design["candidates"][0]
        report = {"execution_mode": "direct_kernel_no_llm", "design": design}
        if args.write:
            if db.query(AgentTask).filter(AgentTask.case_id == case.id, AgentTask.status.in_(["pending", "running"])).first():
                raise ValueError("Case has an active run; retry after it ends")
            session = session_for_case(db, case, None)
            task = AgentTask(case_id=case.id, mode="workbench", goal="直接内核复算（未调用模型）：" + evidence["sources"].get("message", "依据可核对事实复算"), status="running")
            db.add(task)
            db.flush()
            plan = GeneratedContent(case_id=case.id, content_type="plan", model="LaserClaw Python/NumPy", prompt_version="direct-kernel-v34",
                                    content={"title": case.title + " · 实物约束复算", "engineering_design": design, "summary": design["summary"], "execution_mode": "direct_kernel_no_llm"})
            db.add(plan)
            db.flush()
            call = AgentToolCall(task_id=task.id, tool_name="optical_design_solver", status="completed", input_json={"facts": facts, "evidence": evidence, "execution_mode": "direct_kernel_no_llm"},
                                 output_json={"content_id": plan.id, "summary": design["summary"], "search": design["search"]}, latency_ms=int((perf_counter()-started)*1000))
            db.add(call)
            case.parameters = {**(case.parameters or {}), "design_facts": facts}
            db.commit()
            call_ids = [call.id]

            async def recorded_tool(name, raw):
                started = perf_counter()
                parsed = REGISTRY[name][0].model_validate(raw)
                output = await execute(name, parsed, db=db, case=case, task=task, provider=None, session_id=session.id, attachment_ids=[])
                item = AgentToolCall(task_id=task.id, tool_name=name, status="completed", input_json=raw, output_json=output, latency_ms=int((perf_counter()-started)*1000))
                db.add(item)
                db.commit()
                call_ids.append(item.id)
                return output

            try:
                previous = read_project(db, case.id)
                project = await recorded_tool("import_design_project", {"content_id": plan.id, "candidate": 1, "base_revision_id": previous["revision_id"] if previous else None})
                analysis = await recorded_tool("analyze_saved_design", {"content_id": plan.id, "candidate": 1, "mode": "cavity", "samples": 900})
                config = {"system": project["project"]["system"], "x": {"element_index": 1, "parameter": "length_mm", "start": 1, "stop": 20, "count": 41},
                          "y": {"element_index": 5, "parameter": "length_mm", "start": 1, "stop": 200, "count": 81}}
                scan = await recorded_tool("scan_optical_system_2d", config)
                scan_artifact = GeneratedContent(case_id=case.id, content_type="optical_scan", prompt_version="optical-map-v1", content={"project_revision_id": project["revision_id"], "configuration": config, "scan": scan, "summary": "实物约束下的冷腔二维稳定图"})
                db.add(scan_artifact)
                db.flush()
                c = candidate
                summary = ("本次为直接物理内核复算，未调用 LLM；不代表真实模型联调通过。\n\n" + design["summary"] +
                           f"\n\n晶体中心 {design['resolved_inputs']['laser_wavelength_nm']:g} nm 模半径 {c['mode_radius_mm']*1000:.3f} μm（1/e²）。位置以 M1 腔内镀膜面为 z=0。" +
                           f"\n\n已保存设计 #{plan.id}、可编辑工程 #{project['revision_id']}、二维稳定图 #{scan_artifact.id}。在「光学工程」可修改间隙并保存新版本；在「已存光路设计」可查看候选、精确游标和热透镜场景。" +
                           "\n\n事实、假设与目标函数均保存在设计中；此模型未从标称泵浦功率推算热透镜或输出功率。")
                findings = [f"候选 {c['rank']}：M2 后间隙 {c['placement']['output_gap_mm']:g} mm，两镜间距 {c['length_mm']:g} mm，晶体中心模半径 {c['mode_radius_mm']*1000:.3f} μm。" for c in design["candidates"][:3]]
                result = {"status": "partial", "summary": summary, "findings": findings, "facts": [], "questions": [], "evidence_tool_call_ids": call_ids,
                          "assumptions": ["冷腔、近轴、正入射；以所选晶体折射率与偏振模型计算。", "采用已存设计列明的目标模半径；本次比较的是几何与模场，不是最大输出功率。"],
                          "next_steps": ["向腔镜供应商索取 M1 基底材料、中心厚度、背面曲率，以及 M2 的 T@1064 数据。",
                                         "也可记录经过现有两片透镜与 M1 后的 808 nm 光束在多个 z 位置的半径，连同半径定义交给 Agent；新增焦散拟合工具可求实际焦点和等效 M²。",
                                         "热态模场需实际热透镜或测量约束；当前 ∞/500/200/100/50 mm 为敏感性场景。"], "execution_mode": "direct_kernel_no_llm"}
                final = GeneratedContent(case_id=case.id, content_type="workbench", model="LaserClaw Python/NumPy", prompt_version="direct-kernel-v34", content={"workbench": result, "summary": summary, "task_id": task.id, "execution_mode": "direct_kernel_no_llm"})
                db.add(final)
                db.flush()
                task.status, task.final_content_id = "partial", final.id
                db.add(AgentChatMessage(session_id=session.id, role="assistant", content=summary, metadata_json={"workbench_run_id": task.id, "generated_content_id": final.id, "result": result, "execution_mode": "direct_kernel_no_llm"}))
                db.commit()
                report.update(task_id=task.id, plan_id=plan.id, project=project, analysis=analysis, scan={"artifact_id": scan_artifact.id, **scan}, result=result)
            except Exception:
                db.rollback()
                task.status = "failed"
                db.commit()
                raise
        output = Path(args.output)
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        output.with_suffix(".rez").write_text(json.dumps(cold_cavity_schema(candidate, design["resolved_inputs"]["laser_wavelength_nm"]), ensure_ascii=False, indent=2), encoding="utf-8")
        print(json.dumps({"written": args.write, "task_id": report.get("task_id"), "plan_id": report.get("plan_id"), "project_id": report.get("project", {}).get("revision_id"), "output": str(output), "summary": design["summary"]}, ensure_ascii=False))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--case-id", type=int, required=True)
    parser.add_argument("--evidence", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--write", action="store_true")
    asyncio.run(run(parser.parse_args()))
