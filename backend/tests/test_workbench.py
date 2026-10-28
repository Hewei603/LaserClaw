"""Diverse tasks, real tool feedback, error repair and continuation (no live keys)."""
import asyncio
import json
import math
from types import SimpleNamespace

import pytest
import numpy as np
from pydantic import ValidationError
from sqlalchemy.orm import sessionmaker

from app.models import AgentTask, Attachment, ExperimentCase, GeneratedContent
from app.workbench.optics import OpticalSystem, analyze_system, scan_system
from app.providers.tool_calling import openai_turn
from app.workbench import service
from app.workbench.contracts import Finish


def plane_cavity(length=50, radius=100):
    return {"mode": "standing_wave", "wavelength_nm": 1064,
            "elements": [{"name": "M1", "kind": "mirror"}, {"name": "air", "kind": "space", "length_mm": length},
                         {"name": "M2", "kind": "mirror", "radius_mm": radius}]}


def test_general_cavity_matches_analytic_gaussian_solution():
    result = analyze_system(plane_cavity())
    expected_w = math.sqrt(1064e-6 / math.pi * math.sqrt(50 * (100 - 50)))
    assert result["stable_both_planes"]
    for plane in result["planes"].values():
        assert plane["input"]["radius_mm"] == pytest.approx(expected_w, rel=1e-10)
        assert plane["input"]["q_imag_mm"] == pytest.approx(50)
        assert plane["output"]["z_mm"] == 50


def test_slab_uses_physical_axis_and_reduced_diffraction_length():
    system = plane_cavity(length=20, radius=200)
    system["elements"].insert(2, {"name": "crystal", "kind": "space", "length_mm": 30, "n": 2})
    result = analyze_system(system)["planes"]["tangential"]
    expected_w = math.sqrt(1064e-6 / math.pi * math.sqrt(35 * 165))
    assert result["input"]["radius_mm"] == pytest.approx(expected_w)
    assert result["output"]["z_mm"] == 50  # not reduced length 35
    incident = [p for p in result["samples"] if p["n"] == 1][-1]
    transmitted = [p for p in result["samples"] if p["n"] == 2][0]
    assert incident["radius_mm"] == pytest.approx(transmitted["radius_mm"])


def test_single_pass_telescope_and_signed_lens():
    # 4f relay: input waist imaged with exactly 2x magnification.
    system = {"mode": "single_pass", "wavelength_nm": 1064, "input_radius_mm": .2, "elements": [
        {"name": "to L1", "kind": "space", "length_mm": 50}, {"name": "L1", "kind": "lens", "focal_mm": 50},
        {"name": "between", "kind": "space", "length_mm": 150}, {"name": "L2", "kind": "lens", "focal_mm": 100},
        {"name": "image", "kind": "space", "length_mm": 100}]}
    result = analyze_system(system)["planes"]["tangential"]
    assert result["output"]["radius_mm"] == pytest.approx(.4)
    assert result["downstream_waist_in_air"]["distance_from_output_mm"] == pytest.approx(0, abs=1e-10)
    system["elements"][1]["focal_mm"] = -50
    assert analyze_system(system)["planes"]["tangential"]["output"]["radius_mm"] > .4


def test_ring_astigmatism_and_unstable_geometry():
    ring = {"mode": "ring", "wavelength_nm": 1064, "elements": [
        {"name": "leg1", "kind": "space", "length_mm": 50},
        {"name": "M1", "kind": "mirror", "radius_mm": 200, "aoi_deg": 30},
        {"name": "leg2", "kind": "space", "length_mm": 50},
        {"name": "M2", "kind": "mirror", "radius_mm": 200, "aoi_deg": 30}]}
    result = analyze_system(ring)
    assert result["stable_both_planes"]
    assert result["planes"]["tangential"]["input"]["radius_mm"] != result["planes"]["sagittal"]["input"]["radius_mm"]
    result = analyze_system(plane_cavity(200, 100))
    assert not result["stable_both_planes"]
    assert result["planes"]["tangential"]["samples"] == []


def test_scan_preserves_unstable_rows_and_refuses_ineffective_parameters():
    scan = {"system": plane_cavity(), "element_index": 1, "parameter": "length_mm", "start": 1, "stop": 151, "count": 151}
    result = scan_system(scan)
    assert result["stable_count"] == 99
    assert len(result["points"]) == 151
    assert result["points"][99]["tangential"]["stable"] is False
    with pytest.raises(ValueError, match="does not affect"):
        scan_system({**scan, "parameter": "focal_mm"})


@pytest.mark.parametrize("update", [{"input_radius_mm": None}, {"wavelength_nm": float('nan')}, {"input_curvature_mm": 0}])
def test_invalid_optics_inputs_are_not_silent_defaults(update):
    with pytest.raises(ValidationError):
        OpticalSystem.model_validate({"mode": "single_pass", "wavelength_nm": 1064, "input_radius_mm": .2,
                                     "elements": [{"name": "air", "kind": "space", "length_mm": 100}], **update})


def test_finish_requires_actionable_guidance():
    with pytest.raises(ValidationError):
        Finish(status="needs_input", summary="Missing data")
    with pytest.raises(ValidationError):
        Finish(status="unsupported", summary="No tool")


class ScriptedProvider:
    def __init__(self, script):
        self.script = iter(script)
        self.messages = []

    async def agent_turn(self, instructions, messages, tools):
        self.messages.append(json.loads(json.dumps(messages)))
        step = next(self.script)
        if isinstance(step, Exception):
            raise step
        name, args = step(messages) if callable(step) else step
        return {"items": [], "calls": [{"id": f"c{len(self.messages)}", "name": name, "arguments": json.dumps(args)}],
                "_usage": {"provider": "script", "model": "test", "input_tokens": 10, "output_tokens": 5}}


def finish_with_evidence(messages):
    outputs = [json.loads(m["content"]) for m in messages if m["role"] == "tool"]
    ids = [o["tool_call_id"] for o in outputs if o["result"].get("status", "completed") == "completed"]
    return "finish", {"status": "completed", "summary": "已根据实际计算给出结果。", "evidence_tool_call_ids": ids}


@pytest.fixture
def workbench(db, client, monkeypatch):
    monkeypatch.setattr(service, "SessionLocal", sessionmaker(bind=db.get_bind(), expire_on_commit=False))
    case = ExperimentCase(title="多种任务验收", description="用户只有目标和部分信息", cavity_type="custom", goal="理解任务")
    db.add(case)
    db.commit()
    service.ACTIVE_RUNS.clear()
    yield case, client
    service.ACTIVE_RUNS.clear()


def use_script(monkeypatch, script):
    provider = ScriptedProvider(script)
    monkeypatch.setattr(service, "get_ai_provider", lambda: provider)
    return provider


def test_native_tool_loop_repairs_error_then_computes_and_persists(workbench, db, monkeypatch):
    case, client = workbench
    provider = use_script(monkeypatch, [
        ("analyze_optical_system", {"mode": "single_pass"}),
        ("analyze_optical_system", plane_cavity()), finish_with_evidence])
    response = client.post(f"/api/cases/{case.id}/workbench/runs", json={"message": "计算这个腔模"})
    assert response.status_code == 202
    run = client.get(f"/api/cases/{case.id}/workbench").json()["runs"][0]
    assert run["status"] == "completed"
    assert [c["status"] for c in run["tools"]] == ["failed", "completed", "completed"]
    assert "Correct the tool arguments" in provider.messages[1][-1]["content"]
    artifact = db.get(GeneratedContent, run["final_content_id"])
    assert artifact.input_tokens == 30 and artifact.output_tokens == 15
    assert run["tools"][1]["output"]["stable_both_planes"]


def test_missing_data_question_and_followup_reuses_history(workbench, monkeypatch):
    case, client = workbench
    question = {"question": "入射光束半径与波前在哪里测量？", "why": "确定入射 q 参数才能预测焦斑。",
                "how_to_obtain": "用光束分析仪测量两个以上位置的光斑，标注测量间距；也可提供已知束腰尺寸和位置。", "expected_format": "1/e² 半径 mm，位置 mm"}
    use_script(monkeypatch, [("finish", {"status": "needs_input", "summary": "可以确定透镜排列，焦斑需入射束参数。", "questions": [question]})])
    client.post(f"/api/cases/{case.id}/workbench/runs", json={"message": "已知透镜100mm，焦点多大"})
    state = client.get(f"/api/cases/{case.id}/workbench").json()
    assert state["runs"][0]["status"] == "needs_input"
    assert state["runs"][0]["result"]["questions"][0]["how_to_obtain"]
    provider = use_script(monkeypatch, [("analyze_optical_system", {"mode": "single_pass", "wavelength_nm": 1064, "input_radius_mm": .5,
                                                               "elements": [{"kind": "lens", "name": "L", "focal_mm": 100}, {"kind": "space", "name": "air", "length_mm": 100}]}), finish_with_evidence])
    client.post(f"/api/cases/{case.id}/workbench/runs", json={"message": "1064nm，透镜前束腰半径0.5mm"})
    context = json.loads(provider.messages[0][0]["content"])
    assert any(m["content"] == "已知透镜100mm，焦点多大" for m in context["conversation"])
    assert any(m.get("metadata", {}).get("result", {}).get("questions") for m in context["conversation"])


def test_power_data_task_is_not_routed_to_cavity(workbench, monkeypatch):
    case, client = workbench
    pump = list(range(7))
    output = [max(0, .3 * (p - 1)) for p in pump]
    use_script(monkeypatch, [("fit_power_curve", {"pump_w": pump, "output_w": output, "pump_basis": "incident", "data_source": "合成验收数据"}), finish_with_evidence])
    client.post(f"/api/cases/{case.id}/workbench/runs", json={"message": "分析功率数据"})
    run = client.get(f"/api/cases/{case.id}/workbench").json()["runs"][0]
    assert run["tools"][0]["name"] == "fit_power_curve"
    assert run["tools"][0]["output"]["threshold_pump"] == pytest.approx(1)
    assert run["tools"][0]["output"]["slope_efficiency_pct"] == pytest.approx(30)


def test_provider_failure_keeps_tool_output_and_partial_artifact(workbench, monkeypatch):
    case, client = workbench
    use_script(monkeypatch, [("analyze_optical_system", plane_cavity()), RuntimeError("provider down")])
    client.post(f"/api/cases/{case.id}/workbench/runs", json={"message": "计算并解释"})
    run = client.get(f"/api/cases/{case.id}/workbench").json()["runs"][0]
    assert run["status"] == "failed"
    assert run["result"]["status"] == "partial"
    assert run["tools"][0]["output"]["stable_both_planes"]


def test_unknown_tool_and_fake_evidence_are_rejected(workbench, monkeypatch):
    case, client = workbench
    use_script(monkeypatch, [("fake_rezonator", {}), ("finish", {"status": "completed", "summary": "声称完成", "evidence_tool_call_ids": [999]}),
                            ("finish", {"status": "unsupported", "summary": "无法运行这个模型", "next_steps": ["需要增益速率方程工具与标定吸收数据。"]})])
    client.post(f"/api/cases/{case.id}/workbench/runs", json={"message": "预测输出功率"})
    run = client.get(f"/api/cases/{case.id}/workbench").json()["runs"][0]
    assert run["status"] == "unsupported"
    assert [c["status"] for c in run["tools"]][:2] == ["failed", "failed"]


def test_attachment_read_and_case_boundary(workbench, db, monkeypatch, tmp_path):
    case, client = workbench
    path = tmp_path / "data.csv"
    path.write_text("pump_W,output_W\n1,0\n2,0.3\n3,0.6", encoding="utf-8")
    attachment = Attachment(case_id=case.id, filename="data.csv", filepath=str(path), file_type="text/csv")
    db.add(attachment)
    db.commit()
    use_script(monkeypatch, [("read_attachment", {"attachment_id": attachment.id}), finish_with_evidence])
    client.post(f"/api/cases/{case.id}/workbench/runs", json={"message": "读测量文件", "attachment_ids": [attachment.id]})
    run = client.get(f"/api/cases/{case.id}/workbench").json()["runs"][0]
    assert "pump_W" in run["tools"][0]["output"]["text"]
    response = client.post(f"/api/cases/{case.id}/workbench/runs", json={"message": "test", "attachment_ids": [99999]})
    assert response.status_code == 404


def test_round_limit_returns_partial_not_success(workbench, monkeypatch):
    case, client = workbench
    monkeypatch.setattr(service, "MAX_ROUNDS", 2)
    use_script(monkeypatch, [("list_inventory", {}), ("bad_tool", {})])
    client.post(f"/api/cases/{case.id}/workbench/runs", json={"message": "找元件"})
    run = client.get(f"/api/cases/{case.id}/workbench").json()["runs"][0]
    assert run["status"] == "partial" and run["result"]["next_steps"]


def test_cancel_during_model_call_does_not_execute_returned_tool(workbench, db, monkeypatch):
    case, client = workbench

    class CancellingProvider:
        async def agent_turn(self, *_):
            other = service.SessionLocal()
            task = other.query(AgentTask).filter_by(mode="workbench").one()
            task.status = "cancelled"
            other.commit()
            other.close()
            return {"calls": [{"id": "stop", "name": "design_linear_laser", "arguments": "{}"}]}

    monkeypatch.setattr(service, "get_ai_provider", CancellingProvider)
    client.post(f"/api/cases/{case.id}/workbench/runs", json={"message": "run"})
    run = client.get(f"/api/cases/{case.id}/workbench").json()["runs"][0]
    assert run["status"] == "cancelled" and not run["tools"]


def test_responses_preserves_native_reasoning_and_tool_call_outputs():
    captured = {}

    def create(**kwargs):
        captured.update(kwargs)
        item = SimpleNamespace(type="function_call", call_id="new", name="finish", arguments='{"status":"completed","summary":"ok"}')
        item.model_dump = lambda **_: {"type": "function_call", "call_id": item.call_id, "name": item.name, "arguments": item.arguments}
        return SimpleNamespace(status="completed", output=[item], usage=SimpleNamespace(input_tokens=3, output_tokens=4))

    provider = SimpleNamespace(model="gpt-6.1-sol", client=SimpleNamespace(responses=SimpleNamespace(create=create)))
    items = [{"type": "reasoning", "encrypted_content": "opaque", "summary": []}, {"type": "function_call", "call_id": "first", "name": "list_inventory", "arguments": "{}"}]
    result = asyncio.run(openai_turn(provider, "instructions", [{"role": "user", "content": "task"}, {"role": "assistant", "items": items},
                                  {"role": "tool", "call_id": "first", "content": "empty"}], []))
    assert captured["input"][1:3] == items
    assert captured["input"][-1]["call_id"] == "first"
    assert captured["store"] is False and captured["model"] == "gpt-6.1-sol"
    assert result["_usage"]["total_tokens"] == 7


def test_inventory_only_task_and_mock_mode_are_honest(workbench, monkeypatch):
    case, client = workbench
    use_script(monkeypatch, [("list_inventory", {}), finish_with_evidence])
    client.post(f"/api/cases/{case.id}/workbench/runs", json={"message": "只看看元件库，不做仿真"})
    run = client.get(f"/api/cases/{case.id}/workbench").json()["runs"][0]
    assert run["tools"][0]["output"]["total"] == 0
    from app.providers.mock import MockProvider
    monkeypatch.setattr(service, "get_ai_provider", MockProvider)
    client.post(f"/api/cases/{case.id}/workbench/runs", json={"message": "离线继续"})
    run = client.get(f"/api/cases/{case.id}/workbench").json()["runs"][0]
    assert run["status"] == "needs_input" and "离线演示" in run["result"]["summary"]
    assert not any("optical" in call["name"] for call in run["tools"])


def test_followup_can_read_exact_prior_tool_and_history_is_loaded_on_demand(workbench, monkeypatch):
    case, client = workbench
    use_script(monkeypatch, [("analyze_optical_system", plane_cavity()), finish_with_evidence])
    client.post(f"/api/cases/{case.id}/workbench/runs", json={"message": "算冷腔"})
    original = client.get(f"/api/cases/{case.id}/workbench").json()["runs"][0]
    call_id = original["tools"][0]["id"]
    provider = use_script(monkeypatch, [("read_tool_result", {"tool_call_id": call_id, "path": "planes.tangential.input"}), finish_with_evidence])
    client.post(f"/api/cases/{case.id}/workbench/runs", json={"message": "复用前一次的输入面光斑"})
    state = client.get(f"/api/cases/{case.id}/workbench").json()
    assert state["runs"][1]["tools_loaded"] is False
    assert state["runs"][1]["tools"] == []
    current = state["runs"][0]
    assert current["tools"][0]["output"]["output"]["radius_mm"] == pytest.approx(.13013103375)
    assert any(c["id"] == call_id for c in json.loads(provider.messages[0][0]["content"])["saved_tool_results"])
    loaded = client.get(f"/api/cases/{case.id}/workbench/runs/{original['id']}").json()
    assert loaded["tools_loaded"] and loaded["tools"][0]["output"]["stable_both_planes"]


def test_resolved_narrow_waist_is_not_missed_between_uniform_samples():
    wavelength = 1064
    radius = .005
    result = analyze_system({"mode": "single_pass", "wavelength_nm": wavelength, "input_radius_mm": radius,
                             "input_curvature_mm": -10, "samples_per_segment": 2,
                             "elements": [{"kind": "space", "name": "air", "length_mm": 100}]})
    plane = result["planes"]["tangential"]
    assert plane["waists"] and len(plane["samples"]) > 2
    minimum = min(plane["samples"], key=lambda p: p["radius_mm"])
    assert minimum["z_mm"] == pytest.approx(plane["waists"][0]["z_mm"])


def test_context_compaction_preserves_narrow_interior_minima():
    from app.workbench.tools import compact
    points = [{"z_mm": i, "w_mm": 10 - i / 1000} for i in range(200)]
    points[109]["w_mm"] = .003  # missed by uniform 24-point subsampling
    result = compact(points)
    assert 109 in result["sampled_indices"]
    assert any(p["z_mm"] == 109 and p["w_mm"] == .003 for p in result["sampled_items"])


def test_crystal_thermal_lens_conventions_agree_after_conversion():
    from app.physics.design import _round_trip_with_lens
    n, f = 2.164872, 100
    crystal = {"n": n, "thickness_mm": 30, "position_mm": 3}
    legacy = _round_trip_with_lens(40, 1e15, 200, crystal, f)
    system = {"mode": "standing_wave", "wavelength_nm": 1064, "elements": [
        {"name": "M1", "kind": "mirror"}, {"name": "front", "kind": "space", "length_mm": 3},
        {"name": "crystal half", "kind": "space", "length_mm": 15, "n": n},
        {"name": "thermal", "kind": "lens", "focal_mm": f / n},
        {"name": "crystal half", "kind": "space", "length_mm": 15, "n": n},
        {"name": "tail", "kind": "space", "length_mm": 7}, {"name": "M2", "kind": "mirror", "radius_mm": 200}]}
    result = analyze_system(system)
    assert np.allclose(result["planes"]["tangential"]["matrix"], legacy, atol=1e-10)


def test_finished_answer_with_unresolved_questions_downgrades_without_retry(workbench, monkeypatch):
    case, client = workbench
    question = {"question": "实际光斑多大？", "why": "选择匹配模式", "how_to_obtain": "测量焦散", "expected_format": "半径 μm"}
    provider = use_script(monkeypatch, [("analyze_optical_system", plane_cavity()),
                                       ("finish", {"status": "completed", "summary": "冷腔已算，实际匹配待测。", "questions": [question]})])
    client.post(f"/api/cases/{case.id}/workbench/runs", json={"message": "设计并指出缺口"})
    run = client.get(f"/api/cases/{case.id}/workbench").json()["runs"][0]
    assert run["status"] == "partial" and len(provider.messages) == 2
    assert run["result"]["questions"] == [question]
    assert run["tools"][-1]["status"] == "completed"


def test_recover_received_finish_requires_actual_successful_evidence():
    question = {"question": "光斑？", "why": "匹配", "how_to_obtain": "焦散", "expected_format": "μm"}
    error = "Required unanswered questions mean partial or needs_input, not completed"
    tool = SimpleNamespace(id=1, tool_name="analyze_optical_system", status="completed", error_message=None)
    final = SimpleNamespace(id=2, tool_name="finish", status="failed", error_message=error,
                            input_json={"status": "completed", "summary": "已有计算结果", "questions": [question], "evidence_tool_call_ids": [1]})
    result = service.recover_received_finish(SimpleNamespace(tool_calls=[tool, final]))
    assert result["status"] == "partial" and final.status == "completed"
    assert final.output_json["original_validation_error"] == error
    final.status, final.error_message = "failed", error
    final.input_json["evidence_tool_call_ids"] = [999]
    assert service.recover_received_finish(SimpleNamespace(tool_calls=[tool, final])) is None
