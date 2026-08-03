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
    # Robustness must be a MEASURED thermal-lens margin. |m| is not a proxy for
    # it: m = 2*g1*g2 - 1, so a small |m| also describes the near-concentric
    # branch, which dies under a routine thermal lens.
    assert rec["thermal_lens_tolerance_dioptre"] > 0, "recommended cavity must survive some thermal lens"
    assert rec["score_breakdown"]["thermal_tolerance_dioptre"] == rec["thermal_lens_tolerance_dioptre"]
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


def test_thermal_tolerance_distinguishes_the_two_small_m_branches():
    """The bug this guards: |m| ~ 0 on BOTH the short-arm and near-concentric branch.

    Same mirrors, two lengths that both look excellent by |m|; only one survives
    a thermal lens. If robustness ever regresses to an |m| proxy, this fails.
    """
    from app.physics.design import thermal_lens_tolerance
    from app.physics.toolkit import _analyze_length

    crystal = {"n": 1.8147, "thickness_mm": 10, "position_mm": 20}
    m_short = abs(_analyze_length(120.0, 400.0, 400.0, 1064.0, crystal)["stability_m"])
    m_conc = abs(_analyze_length(685.0, 400.0, 400.0, 1064.0, crystal)["stability_m"])
    assert m_short < 0.1 and m_conc < 0.1, "both look equally 'safe' by |m|"

    short_arm = thermal_lens_tolerance(120.0, 400.0, 400.0, crystal)
    near_concentric = thermal_lens_tolerance(685.0, 400.0, 400.0, crystal)
    assert short_arm > 3 * near_concentric, (
        f"|m| says {m_short:.3f} vs {m_conc:.3f} (indistinguishable) but the real "
        f"margins are {short_arm} D vs {near_concentric} D — robustness must be measured"
    )


# --- the kernel must actually reach the model ---------------------------------
#
# Asserting only on the API response is not enough: `computed_physics` is also
# attached to the response after generation, so a build that never put the
# numbers in the PROMPT would still pass. These capture what the provider was
# handed, which is the only thing that grounds the generated prose.

@pytest.fixture
def captured_plan_input(monkeypatch):
    """Record the case_data every generate_plan call receives."""
    from app.providers.mock import MockProvider

    seen: list[dict] = []
    original = MockProvider.generate_plan

    async def spy(self, case_data):
        seen.append(case_data)
        return await original(self, case_data)

    monkeypatch.setattr(MockProvider, "generate_plan", spy)
    return seen


def _make_case(client, parameters, title="kernel injection"):
    resp = client.post("/api/cases", json={
        "title": title, "cavity_type": "linear", "goal": "确定腔长与束腰",
        "parameters": parameters,
    })
    assert resp.status_code in (200, 201), resp.text
    return resp.json()["id"]


def test_plan_prompt_receives_computed_geometry(client, captured_plan_input):
    case_id = _make_case(client, {
        "wavelength_nm": 1064, "R1_mm": "flat", "R2_mm": 400,
        "L_scan_mm": {"start": 50, "stop": 500, "step": 10},
    })
    resp = client.post(f"/api/cases/{case_id}/generate-plan", json={"use_rag": False})
    assert resp.status_code == 200, resp.text

    assert len(captured_plan_input) == 1, "physics must be computed exactly once per plan"
    prompt_physics = captured_plan_input[0].get("computed_physics")
    assert prompt_physics, "the model was given no computed physics at all"
    length = prompt_physics["results"]["cavity_design"]["recommended_length_mm"]
    assert isinstance(length, (int, float)) and length > 0
    # And what the user is shown must be the same computation, not a second one.
    assert resp.json()["content"]["computed_physics"] == prompt_physics


def test_plan_prompt_receives_searched_geometry_when_user_gives_no_mirrors(
    client, captured_plan_input
):
    """The real case: only a wavelength and a crystal. LaserClaw must design it."""
    case_id = _make_case(client, {
        "wavelength_nm": 1064,
        "crystal": {"n": 1.8147, "thickness_mm": 10, "position_mm": 20},
    })
    resp = client.post(f"/api/cases/{case_id}/generate-plan", json={"use_rag": False})
    assert resp.status_code == 200, resp.text

    search = captured_plan_input[0]["computed_physics"]["results"]["cavity_design_search"]
    rec = search["recommended"]
    assert rec["length_mm"] > 0
    assert rec["element_placement"], "the model needs concrete element positions to write a plan"
    assert search["wavelength_nm"] == 1064, "computed values must carry their wavelength"


def test_agent_plan_task_receives_computed_physics(client, captured_plan_input):
    """The agent path must be grounded identically to the REST path."""
    case_id = _make_case(client, {
        "wavelength_nm": 1064, "R1_mm": "flat", "R2_mm": 400,
        "L_scan_mm": {"start": 50, "stop": 500, "step": 10},
    })
    resp = client.post("/api/agent/tasks", json={
        "case_id": case_id, "goal": "给出可搭建的腔长与元件位置", "mode": "plan",
    })
    assert resp.status_code in (200, 201), resp.text

    assert captured_plan_input, "the agent generated a plan without calling the physics kernel"
    physics = captured_plan_input[-1].get("computed_physics")
    assert physics and physics["available"] is True
    assert physics["results"]["cavity_design"]["recommended_length_mm"] > 0

    # The SAVED artifact must carry the kernel result too — the plan tab's
    # green kernel box and red "unverified" warning both read it, and the
    # provider only echoes prose, never this key.
    contents = client.get(f"/api/cases/{case_id}/generated-contents").json()
    plans = [c for c in contents if c["content_type"] == "plan"]
    assert plans and plans[-1]["content"].get("computed_physics"), \
        "agent-generated plan saved without computed_physics: the audit box disappears"


def test_agent_plan_search_is_constrained_to_the_inventory(client, captured_plan_input, db):
    """The agent path must search the mirrors the lab owns, like the REST path.

    A plan recommending a curvature nobody has sends the student to component
    matching to be told the mirror does not exist.
    """
    from app.models import InventoryItem

    db.add(InventoryItem(name="R=777 特殊腔镜", category="mirror",
                         roc_mm=777.0, quantity=1, condition="ok",
                         source_file="stock.xlsx"))
    # A mirror a human marked broken must NOT seed the search, whatever the
    # workbook text said (resolve_condition: human verdict first).
    db.add(InventoryItem(name="R=333 崩边", category="mirror",
                         roc_mm=333.0, quantity=1, condition="ok",
                         condition_manual="damaged", source_file="stock.xlsx"))
    db.commit()

    case_id = _make_case(client, {"wavelength_nm": 1064})
    resp = client.post("/api/agent/tasks", json={
        "case_id": case_id, "goal": "帮我设计一个腔", "mode": "plan",
    })
    assert resp.status_code in (200, 201), resp.text

    space = captured_plan_input[-1]["computed_physics"]["results"]["cavity_design_search"]["search_space"]
    assert space["roc_source"] == "lab inventory", \
        "agent path fell back to the catalogue while the lab has mirrors"
    assert 777.0 in space["candidate_rocs"]
    assert 333.0 not in space["candidate_rocs"], \
        "a manually-damaged mirror seeded the design search"


def test_plan_prompt_says_unknown_rather_than_letting_the_model_guess(
    client, captured_plan_input
):
    case_id = _make_case(client, {"note": "no physics here"})
    resp = client.post(f"/api/cases/{case_id}/generate-plan", json={"use_rag": False})
    assert resp.status_code == 200, resp.text

    physics = captured_plan_input[0]["computed_physics"]
    assert physics["available"] is False
    assert "Do not invent" in physics["note"]
