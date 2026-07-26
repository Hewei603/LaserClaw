"""End-to-end demo: an experiment case flowing through the agent + physics tools.

Creates an isolated in-memory workspace (SQLite + mock LLM provider so the run
is deterministic and needs no API keys), then walks one realistic case through
the full workflow:

  1. create the experiment case (808 pump -> Nd:YAG 1064 -> LBO SHG 532)
  2. index a lab document into global knowledge (RAG)
  3. chat in Chinese -> show how the request is routed to a tool mode
  4. run an agent task that CALLS the deterministic cavity-design tool
     (length scan -> stable windows -> recommended mirror spacing + placement)
  5. run the phase-matching and coating tools the same way
  6. dump the persisted trace: steps, tool calls, latencies, citations

Run:  cd backend && py scripts/demo_physics_case.py
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))

# Isolated deterministic environment (must be set before importing the app).
os.environ["DATABASE_URL"] = "sqlite://"
os.environ["AI_PROVIDER"] = "mock"
os.environ["EMBEDDING_PROVIDER"] = "local"
os.environ["RETRIEVAL_BACKEND"] = "sql_json"
os.environ["RERANKER_PROVIDER"] = "none"
os.environ["AUTO_CREATE_TABLES"] = "false"
os.environ.pop("OPENAI_API_KEY", None)
os.environ.pop("ANTHROPIC_API_KEY", None)

from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import create_engine  # noqa: E402
from sqlalchemy.orm import sessionmaker  # noqa: E402
from sqlalchemy.pool import StaticPool  # noqa: E402

from app.config import get_settings  # noqa: E402

get_settings.cache_clear()

from app import models  # noqa: E402, F401
from app.database import Base, get_db  # noqa: E402
from app.main import app  # noqa: E402

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
Base.metadata.create_all(bind=engine)
Session = sessionmaker(autocommit=False, autoflush=False, bind=engine)
_db = Session()


def _override_get_db():
    try:
        yield _db
    finally:
        pass


app.dependency_overrides[get_db] = _override_get_db
client = TestClient(app)


def section(title: str) -> None:
    print("\n" + "=" * 78)
    print(f"  {title}")
    print("=" * 78)


def show(obj, keys=None, indent=2) -> None:
    if keys:
        obj = {k: obj.get(k) for k in keys if k in obj}
    print(json.dumps(obj, ensure_ascii=False, indent=indent, default=str))


section("STEP 1  创建实验 Case（参数随 Case 持久化，工具可直接取用）")
case_payload = {
    "title": "808nm 泵浦 Nd:YAG 1064nm，LBO 腔内倍频 532nm",
    "description": (
        "半导体 808nm 泵浦 Nd:YAG 晶体产生 1064nm 基频光，计划用 LBO I 类相位匹配腔内倍频到 532nm。"
        "需要设计线性腔：平面输入镜 + R=500mm 凹面输出镜，Nd:YAG 晶体长 10mm 贴近输入镜。"
        "目标是在晶体附近获得约 0.25mm 束腰以提高倍频效率。"
    ),
    "cavity_type": "linear",
    "goal": "确定稳定腔长、束腰大小与各元件摆放位置，并确认 LBO 倍频相位匹配角。",
    "symptoms": [],
    "parameters": {
        "wavelength_nm": 1064,
        "R1_mm": "flat",
        "R2_mm": 500,
        "L_scan_mm": {"start": 100, "stop": 600, "step": 10},
        "target_waist_mm": 0.25,
        "crystal": {"n": 1.8147, "thickness_mm": 10, "position_mm": 20},
    },
}
case = client.post("/api/cases", json=case_payload).json()
print(f"Case #{case['id']}: {case['title']}")
print(f"parameters: {json.dumps(case['parameters'], ensure_ascii=False)}")

section("STEP 2  上传实验室文档到全局知识库（供 RAG 引用）")
doc = BACKEND.parent / "docs" / "evals" / "synthetic_laser_docs" / "laser_safety_sop.md"
with open(doc, "rb") as fh:
    up = client.post(
        "/api/knowledge/sources/upload",
        files={"file": (doc.name, fh, "text/markdown")},
        headers={"x-user-role": "reviewer", "x-user-id": "98"},
    )
print(f"upload: HTTP {up.status_code} -> source #{up.json().get('id')} '{up.json().get('title')}'")

section("STEP 3  中文自然语言请求 -> Agent 意图路由")
chat = client.post(
    "/api/agent/chat",
    json={"case_id": case["id"],
          "message": "帮我设计一个谐振腔，扫描腔长找到稳区，算出束腰和每个元件的摆放位置"},
).json()
print("用户消息:  帮我设计一个谐振腔，扫描腔长找到稳区，算出束腰和每个元件的摆放位置")
print(f"路由结果:  routed_mode = {chat['routed_mode']}   (session #{chat['session_id']})")
print(f"生成内容:  generated_content_id = {chat.get('generated_content_id')}")

section("STEP 4  Agent 任务执行轨迹（步骤 -> 工具调用 -> 确定性计算）")
task = client.get(f"/api/agent/tasks?case_id={case['id']}").json()[0]
print(f"AgentTask #{task['id']}  mode={task['mode']}  status={task['status']}  risk={task['risk_level']}")
print("\n-- 计划步骤 (AgentStep) --")
for s in task["steps"]:
    print(f"  [{s['step_index']}] {s['title']}  -> {s['status']}: {s.get('result_summary') or ''}")
print("\n-- 工具调用 (AgentToolCall) --")
for c in task["tool_calls"]:
    print(f"  {c['tool_name']:28s} status={c['status']} latency={c['latency_ms']}ms")

compute = next(c for c in task["tool_calls"] if c["tool_name"] == "compute_cavity_design")
result = compute["output_json"]

section("STEP 5  物理计算结果：腔长扫描 -> 稳区 -> 推荐几何")
print(f"summary: {result['summary']}")
print(f"stable windows (mm): {result['scan']['stable_windows_mm']}")
print("\n推荐几何:")
show(result["recommended"], keys=["criterion", "length_mm", "stability_m", "waist_w0_mm",
                                  "w_on_mirror1_mm", "w_on_mirror2_mm", "w_in_crystal_mm"])
print("\n元件摆放位置 (从 M1 起):")
for p in result["placement"]:
    print(f"  {p['element']:20s} @ {p['position_mm']} mm")
print("\n各面光斑 (推荐腔长下):")
for s in result["recommended"].get("spots", []):
    print(f"  {s['at']:24s} w = {s['w_mm']} mm")

section("STEP 6  相位匹配工具（LBO 1064 -> 532 倍频角）")
pm_module = client.post(
    f"/api/cases/{case['id']}/modules",
    json={"module_type": "phase_match",
          "config_json": {"crystal": "lbo", "lambda1_nm": 1064, "pm_type": "I"}},
).json()
pm_run = client.post(f"/api/cases/modules/{pm_module['id']}/run", json={"config_json": {}}).json()
pm = pm_run["result_json"]
print(f"summary: {pm['summary']}")
for sol in pm["solutions"]:
    if sol["theta_deg"] is not None:
        print(f"  {sol['plane']} plane: theta={sol['theta_deg']} phi={sol['phi_deg']} "
              f"pol={sol['notes'].split('pol ')[-1].split('.')[0]} conf={sol['confidence']}")

section("STEP 7  镀膜工具（1123nm 标称 HR 能否用于 1064nm？）")
ct_module = client.post(
    f"/api/cases/{case['id']}/modules",
    json={"module_type": "coating_tmm",
          "config_json": {"nominal": {"function": "HR", "design_wavelength_nm": 1123},
                          "query_wavelengths_nm": [1064], "aoi_deg": 0}},
).json()
ct_run = client.post(f"/api/cases/modules/{ct_module['id']}/run", json={"config_json": {}}).json()
ct = ct_run["result_json"]
print(f"summary: {ct['summary']}")
q = ct["query_results"][0]
print(f"1064nm 位置: {q['band_position']}  边缘裕度: {q['margin_to_edge_nm']} nm  "
      f"置信度: {ct['confidence']}  建议实测: {ct['recommend_measurement']}")

section("STEP 8  RAG 引用与审计（citations + 可回放 trace 已入库）")
content = client.get(f"/api/cases/{case['id']}/generated-contents").json()
print(f"generated contents: {len(content)} 条")
for g in content[:2]:
    cites = (g.get("content") or {}).get("citations", [])
    print(f"  #{g['id']} {g['content_type']}: {len(cites)} citation(s)")
    for c in cites[:2]:
        print(f"      - [{c.get('source_type')}] {c.get('title')} (score {c.get('score')})")
print("\n工作流复盘: 意图路由(确定性) -> 计划(4步) -> RAG检索 -> 工具计算(纯物理) -> 结果+引用入库(可审计)")
print("说明: 本演示用 mock LLM 保证确定性; 接入真实 API key 后自然语言摘要更丰富, 工具计算结果完全相同。")
