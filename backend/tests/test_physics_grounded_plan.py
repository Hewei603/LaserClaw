"""The experiment plan must be grounded in the deterministic physics kernel.

These lock the v2 contract: geometry and phase-matching angles handed to the
model come from `app.physics`, and the ReZonator draft feature is gone.
"""
import pytest

from app.physics.case_context import compute_case_physics


def test_cavity_parameters_produce_computed_geometry():
    facts = compute_case_physics({
        "wavelength_nm": 1064,
        "R1_mm": "flat",
        "R2_mm": 400,
        "L_scan_mm": {"start": 50, "stop": 500, "step": 10},
        "target_waist_mm": 0.25,
        "crystal": {"n": 1.8147, "thickness_mm": 10, "position_mm": 20},
    })
    assert facts["available"] is True
    assert "cavity_design" in facts["tools_run"]
    cav = facts["results"]["cavity_design"]
    assert cav["recommended_length_mm"] > 0
    assert cav["waist_w0_mm"] > 0
    assert cav["element_placement"], "plan needs element positions"
    assert "deterministic physics kernel" in facts["note"]


def test_nonlinear_parameters_produce_phase_match_angles():
    facts = compute_case_physics({
        "wavelength_nm": 1064,
        "nonlinear_crystal": "lbo",
        "shg_pm_type": "I",
        "R1_mm": "flat",
        "R2_mm": 400,
    })
    pm = facts["results"].get("phase_matching", {}).get("SHG")
    assert pm, "SHG phase matching should be computed"
    assert pm["solutions"][0]["theta_deg"] is not None


def test_no_parameters_refuses_to_invent_geometry():
    facts = compute_case_physics({})
    assert facts["available"] is False
    assert facts["results"] == {}
    assert "Do not invent" in facts["note"]


def test_bad_parameters_are_skipped_not_guessed():
    facts = compute_case_physics({"wavelength_nm": "not-a-number", "R2_mm": "oops"})
    assert facts["available"] is False


def test_plan_endpoint_attaches_computed_physics(client):
    case = client.post("/api/cases", json={
        "title": "Nd:YAG 1064 平凹腔", "cavity_type": "linear",
        "goal": "确定腔长与束腰",
        "parameters": {"wavelength_nm": 1064, "R1_mm": "flat", "R2_mm": 400,
                       "L_scan_mm": {"start": 50, "stop": 500, "step": 10}},
    })
    case_id = case.json()["id"]
    resp = client.post(f"/api/cases/{case_id}/generate-plan", json={"use_rag": False})
    assert resp.status_code == 200, resp.text
    physics = resp.json()["content"]["computed_physics"]
    assert physics["available"] is True
    assert physics["results"]["cavity_design"]["recommended_length_mm"] > 0


# --- ReZonator draft feature is fully removed --------------------------------

def test_rezonator_endpoint_is_gone(client):
    case = client.post("/api/cases", json={
        "title": "x", "cavity_type": "linear", "goal": "g"}).json()
    resp = client.post(f"/api/cases/{case['id']}/generate-rezonator")
    assert resp.status_code == 404


def test_rezonator_agent_mode_rejected(client):
    case = client.post("/api/cases", json={
        "title": "x", "cavity_type": "linear", "goal": "g"}).json()
    resp = client.post("/api/agent/tasks",
                       json={"case_id": case["id"], "goal": "g", "mode": "rezonator"})
    assert resp.status_code == 422


def test_providers_no_longer_expose_rezonator():
    from app.providers.mock import MockProvider

    assert not hasattr(MockProvider(), "generate_rezonator_schema")


def test_rezonator_artifact_schema_removed():
    from app.agent.schemas import _SCHEMA_MAP

    assert "rezonator" not in _SCHEMA_MAP


@pytest.mark.parametrize("phrase", ["腔稳定性分析", "曲率半径参数", "谐振腔设计"])
def test_cavity_phrases_route_to_cavity_design(phrase):
    from app.agent.router import TOOL_CAVITY_DESIGN, route_sync

    assert route_sync(phrase).selected_tool == TOOL_CAVITY_DESIGN


# --- design search: the user gives almost nothing, LaserClaw finds a geometry ---

def test_design_search_when_user_gives_no_mirrors():
    """The common real case: a wavelength and a crystal, no mirrors chosen yet."""
    facts = compute_case_physics({
        "wavelength_nm": 1064,
        "crystal": {"n": 1.8147, "thickness_mm": 10, "position_mm": 20},
    })
    assert facts["available"] is True
    assert "cavity_design_search" in facts["tools_run"]
    search = facts["results"]["cavity_design_search"]
    rec = search["recommended"]
    assert rec["length_mm"] > 0 and rec["waist_w0_mm"] > 0
    assert abs(rec["stability_m"]) <= 0.85, "must keep margin from the stability edge"
    names = [p["element"] for p in rec["element_placement"]]
    assert "Crystal entrance" in names and "Crystal exit" in names, "plan needs crystal placement"
    assert search["search_space"]["stable_configurations_found"] > 0
    assert search["objective"] and search["caveats"], "ranking must be auditable"


def test_design_search_respects_lab_inventory():
    """A design built from mirrors nobody owns is useless."""
    owned = [200.0, 500.0, "flat"]
    facts = compute_case_physics(
        {"wavelength_nm": 1064, "crystal": {"n": 1.8147, "thickness_mm": 10, "position_mm": 20}},
        available_rocs=owned,
    )
    search = facts["results"]["cavity_design_search"]
    assert search["search_space"]["roc_source"] == "lab inventory"
    for cand in [search["recommended"], *search["alternatives"]]:
        for label in (cand["R1"], cand["R2"]):
            assert label == "flat" or any(f"R={r:g}mm" == label for r in owned if r != "flat")


def test_design_search_needs_a_physical_hint():
    """With no wavelength at all we must not invent one."""
    assert compute_case_physics({"note": "nothing physical here"})["available"] is False
