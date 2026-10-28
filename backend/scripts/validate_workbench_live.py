"""Explicit opt-in live Agent evaluation, using a temporary isolated database.

Run with --live. Provider configuration is read normally; no credentials are
printed. Synthetic tasks never enter the user's experiment database.
"""
import argparse
import asyncio
import json
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import create_engine  # noqa: E402
from sqlalchemy.orm import sessionmaker  # noqa: E402

from app.database import Base  # noqa: E402
from app.models import AgentChatMessage, AgentTask, AgentToolCall, ExperimentCase  # noqa: E402
from app.providers import get_ai_provider  # noqa: E402
from app.workbench import service  # noqa: E402

TASKS = [
    ("4f 扩束验证", "这是合成验收任务。1064nm 理想高斯束，输入面为束腰，1/e²半径0.2mm。输入面后50mm放f50薄透镜，再后150mm放f100薄透镜，再后100mm为观察面。计算观察面光斑与波前，给出图和元件位置。", "analyze_optical_system"),
    ("测量曲线分析", "这是合成验收数据。入射泵浦/W=[0,1,2,3,4,5,6]，输出/W=[0,0,0.3,0.6,0.9,1.2,1.5]。请计算阈值、斜率效率并解释，不需要设计谐振腔。", "fit_power_curve"),
    ("能力边界与补测", "只有一块 Nd:YAG 晶体和一个标称6W的808nm泵浦源。我想得到晶体三维温度场、热应力分布与连续工作10000小时后的寿命，请给定量结果。你能算哪些，缺什么，怎样去获得缺的信息？", None),
    ("环形腔参数扫描", "合成验收：1064nm平面四镜环形腔，按光路顺序M1凹面R200mm入射角15度、空气50mm、M2平面、空气50mm、M3凹面R200mm入射角15度、空气50mm、M4平面、空气50mm回M1。所有折转共面。先算T/S稳定性与光斑，再把M2到M3距离从20扫到120mm，其余固定，比较两平面稳定区。不要用平凹直线腔代替。", "scan_optical_system"),
]


async def main(output):
    provider = get_ai_provider()
    print(f"Live provider: {type(provider).__name__}, model: {getattr(provider, 'model', 'mock')}", flush=True)
    if type(provider).__name__ == "MockProvider":
        raise RuntimeError("Live evaluation requires a configured real provider")
    reports = []
    with tempfile.TemporaryDirectory(prefix="laserclaw-workbench-live-") as directory:
        engine = create_engine(f"sqlite:///{Path(directory) / 'eval.db'}", connect_args={"check_same_thread": False})
        Base.metadata.create_all(engine)
        service.SessionLocal = sessionmaker(bind=engine, expire_on_commit=False)
        for title, goal, expected in TASKS:
            with service.SessionLocal() as db:
                case = ExperimentCase(title=title, description="Synthetic isolated acceptance test", cavity_type="custom", goal=goal)
                db.add(case)
                db.flush()
                session = service.session_for_case(db, case, None)
                task = AgentTask(case_id=case.id, goal=goal, mode="workbench", status="pending")
                db.add(task)
                db.flush()
                task_id = task.id
                db.add(AgentChatMessage(session_id=session.id, role="user", content=goal))
                db.add(AgentToolCall(task_id=task.id, tool_name="workbench_request", input_json={"session_id": session.id, "attachment_ids": []}, output_json={}))
                db.commit()
            await service.execute_run(task_id)
            with service.SessionLocal() as db:
                task = db.get(AgentTask, task_id)
                calls = [c for c in task.tool_calls if c.tool_name not in {"finish", "workbench_request"}]
                result = task.final_content.content["workbench"] if task.final_content else {}
                passed = task.status not in {"failed", "pending", "running"}
                if expected:
                    passed = passed and any(c.tool_name == expected and c.status == "completed" for c in calls)
                else:
                    passed = passed and result.get("status") in {"needs_input", "unsupported", "partial"} and bool(result.get("questions") or result.get("next_steps"))
                report = {"title": title, "status": task.status, "passed": passed, "result": result,
                          "tools": [{"name": c.tool_name, "status": c.status, "input": c.input_json, "output": c.output_json, "error": c.error_message} for c in calls],
                          "model": task.final_content.model if task.final_content else None}
                reports.append(report)
                print(json.dumps({"title": title, "status": task.status, "passed": passed, "tools": [c.tool_name for c in calls]}, ensure_ascii=False), flush=True)
                Path(output).write_text(json.dumps(reports, ensure_ascii=False, indent=2), encoding="utf-8")
        engine.dispose()
    if not all(r["passed"] for r in reports):
        raise SystemExit(1)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--live", action="store_true", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    asyncio.run(main(args.output))
