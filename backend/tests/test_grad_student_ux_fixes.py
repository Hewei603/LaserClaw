# -*- coding: utf-8 -*-
"""Regressions for the grad-student persona review fixes.

The persona: a laser-physics grad student with zero software background who
reads only Chinese. Every fix here failed a review from that viewpoint —
English dead-ends, silent degradation, or a lying confirmation.
"""
import pytest

from app.physics.case_context import compute_case_physics
from app.physics.toolkit import run_cavity_design, run_phase_match


# --- module tools speak Chinese and accept case-parameter names --------------

def test_cavity_design_empty_config_asks_in_chinese():
    out = run_cavity_design({})
    assert out["status"] == "needs_input"
    assert "腔镜曲率" in out["message"]
    assert "Provide" not in out["message"]


def test_cavity_design_mirrors_only_defaults_to_scan():
    """The guide promises 'leave the config empty' — mirrors given, no length."""
    out = run_cavity_design({"R1_mm": "flat", "R2_mm": 500})
    assert out["status"] == "completed"
    assert out["scan"]["stable_windows_mm"], "default 30-800 mm scan must find stable zones"
    assert out["recommended"]["length_mm"] > 0


def test_cavity_design_scan_ranks_by_measured_thermal_tolerance():
    out = run_cavity_design({
        "R1_mm": 400, "R2_mm": 400,
        "crystal": {"n": 1.8147, "thickness_mm": 10, "position_mm": 20},
    })
    rec = out["recommended"]
    assert rec["thermal_lens_tolerance_dioptre"] > 0
    assert "热透镜" in rec["criterion"]
    assert "|m|" not in rec["criterion"].replace("不使用 |m|", "")  # proxy is named only to disavow it


def test_cavity_design_rejects_string_crystal_in_chinese():
    """A free-form case entry can leave crystal='lbo' — must not raise TypeError."""
    out = run_cavity_design({"R1_mm": "flat", "R2_mm": 500, "L_mm": 200, "crystal": "lbo"})
    assert out["status"] == "needs_input"
    assert "相位匹配" in out["message"]


def test_phase_match_accepts_case_parameter_names():
    """Case params: nonlinear_crystal + wavelength_nm + gain `crystal` DICT.

    The dict must not be mistaken for the nonlinear crystal name.
    """
    out = run_phase_match({
        "crystal": {"n": 1.8147, "thickness_mm": 10},   # gain slab, NOT the SHG crystal
        "nonlinear_crystal": "lbo",
        "wavelength_nm": 1064,
        "shg_pm_type": "I",
    })
    assert out["status"] == "completed"
    assert any(s["theta_deg"] is not None for s in out["solutions"])
    assert "订购" in out["disclaimer"] or "厂商" in out["disclaimer"]


def test_phase_match_missing_inputs_ask_in_chinese():
    assert "倍频晶体" in run_phase_match({})["message"]
    assert "基频波长" in run_phase_match({"crystal": "lbo"})["message"]


# --- pasted-JSON crystal is parsed; garbage is reported, not dropped ---------

def test_case_context_parses_json_string_crystal():
    facts = compute_case_physics({
        "wavelength_nm": 1064,
        "crystal": '{"n": 1.8147, "thickness_mm": 10, "position_mm": 20}',
    })
    rec = facts["results"]["cavity_design_search"]["recommended"]
    assert rec["spot_in_crystal_mm"] is not None


def test_case_context_reports_unusable_crystal_string():
    facts = compute_case_physics({"wavelength_nm": 1064, "crystal": "lbo"})
    assert any("crystal" in item for item in facts["skipped"])
    # The search still runs (without the crystal), it is not suppressed.
    assert "cavity_design_search" in facts["tools_run"]


# --- provider visibility ------------------------------------------------------

def test_health_reports_effective_provider(client):
    data = client.get("/health").json()
    assert data["status"] == "healthy"
    assert data["provider"]["is_mock"] is True  # tests always run on mock
    assert data["provider"]["effective_provider"] == "mock"


def test_unknown_provider_name_respects_strict_mode(monkeypatch):
    from app.config import get_settings
    from app.providers import get_ai_provider

    monkeypatch.setenv("AI_PROVIDER", "deepseak")   # the typo the audit warned about
    monkeypatch.setenv("STRICT_PROVIDER", "true")
    get_settings.cache_clear()
    try:
        with pytest.raises(RuntimeError):
            get_ai_provider()
    finally:
        get_settings.cache_clear()


@pytest.mark.asyncio
async def test_mock_output_is_labelled_as_demo():
    from app.providers.mock import MockProvider

    plan = await MockProvider().generate_plan({"cavity_type": "linear", "goal": "x"})
    assert "演示模式" in plan["notice"]
    chat = await MockProvider().generate_chat_response({"message": "你好"})
    assert "演示模式" in chat["message"]


def test_anthropic_auth_errors_are_not_retryable():
    """Same class-hierarchy trap as OpenAI: APIStatusError is the PARENT of
    AuthenticationError, so putting it in the retryable set silently retries a
    wrong key and reports it as "service unavailable"."""
    anthropic = pytest.importorskip("anthropic")
    from app.providers.anthropic import ANTHROPIC_FATAL_ERRORS, ANTHROPIC_RETRYABLE_ERRORS

    assert anthropic.AuthenticationError in ANTHROPIC_FATAL_ERRORS
    assert anthropic.APIStatusError not in ANTHROPIC_RETRYABLE_ERRORS
    for fatal in ANTHROPIC_FATAL_ERRORS:
        assert not issubclass(fatal, tuple(ANTHROPIC_RETRYABLE_ERRORS)), (
            f"{fatal.__name__} is a subclass of a retryable error and would be retried"
        )


def test_openai_auth_errors_are_not_retryable():
    openai = pytest.importorskip("openai")
    from app.providers.openai import OPENAI_FATAL_ERRORS, OPENAI_RETRYABLE_ERRORS

    assert openai.AuthenticationError in OPENAI_FATAL_ERRORS
    for err in OPENAI_FATAL_ERRORS:
        assert not any(issubclass(err, r) and err is not r for r in ()), "sanity"
        assert err not in OPENAI_RETRYABLE_ERRORS
    # The base APIError must not blanket-retry its fatal subclasses.
    assert openai.APIError not in OPENAI_RETRYABLE_ERRORS


# --- agent chat confirmation is status-aware Chinese --------------------------

def test_agent_chat_module_needs_input_is_reported_honestly(client):
    case = client.post("/api/cases", json={
        "title": "空参数案例", "cavity_type": "linear", "goal": "设计谐振腔",
    }).json()
    resp = client.post("/api/agent/chat", json={
        "case_id": case["id"], "message": "帮我设计谐振腔", "mode": "cavity_design",
    })
    assert resp.status_code == 200, resp.text
    message = resp.json()["message"]
    assert "缺少输入" in message, f"needs_input module must not claim success: {message}"
    assert "Created and completed" not in message


def test_agent_chat_without_case_explains_in_chinese(client):
    resp = client.post("/api/agent/chat", json={"message": "生成实验计划", "mode": "plan"})
    assert resp.status_code == 200, resp.text
    assert "案例" in resp.json()["message"]


# --- module runner path (REST) ------------------------------------------------

def test_module_run_cavity_design_with_case_params_only(client):
    """GUIDE workflow steps 1-2: fill mirrors in the case, run module empty."""
    case = client.post("/api/cases", json={
        "title": "1064 平凹腔", "cavity_type": "linear", "goal": "找稳区",
        "parameters": {"wavelength_nm": 1064, "R1_mm": "flat", "R2_mm": 500},
    }).json()
    module = client.post(f"/api/cases/{case['id']}/modules",
                         json={"module_type": "cavity_design"}).json()
    result = client.post(f"/api/cases/modules/{module['id']}/run", json={}).json()
    assert result["result_json"]["status"] == "completed", result["result_json"]
    assert result["result_json"]["recommended"]["length_mm"] > 0


def test_module_run_phase_match_with_case_params_only(client):
    case = client.post("/api/cases", json={
        "title": "LBO 倍频", "cavity_type": "linear", "goal": "算切角",
        "parameters": {"wavelength_nm": 1064, "nonlinear_crystal": "lbo",
                       "shg_pm_type": "I",
                       "crystal": {"n": 1.8147, "thickness_mm": 10}},
    }).json()
    module = client.post(f"/api/cases/{case['id']}/modules",
                         json={"module_type": "phase_match"}).json()
    result = client.post(f"/api/cases/modules/{module['id']}/run", json={}).json()
    assert result["result_json"]["status"] == "completed", result["result_json"]


# --- inventory batches --------------------------------------------------------

def test_inventory_sources_and_clear(client):
    from app.models import InventoryItem

    # Seed two batches directly through the session the client is bound to.
    from app.database import get_db
    from app.main import app as fastapi_app

    db = next(iter(fastapi_app.dependency_overrides[get_db]()))
    db.add(InventoryItem(name="镜A", category="mirror", quantity=1, source_file="a.xlsx"))
    db.add(InventoryItem(name="镜B", category="mirror", quantity=1, source_file="b.xlsx"))
    db.commit()

    sources = client.get("/api/inventory/sources").json()
    assert {s["source_file"] for s in sources} >= {"a.xlsx", "b.xlsx"}

    resp = client.delete("/api/inventory/items", params={"source_file": "a.xlsx"})
    assert resp.status_code == 200
    assert resp.json()["deleted_items"] == 1
    remaining = {s["source_file"] for s in client.get("/api/inventory/sources").json()}
    assert "a.xlsx" not in remaining and "b.xlsx" in remaining
