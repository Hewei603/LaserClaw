"""Regression tests for the actual 808 nm composite Nd:YVO4 design workflow."""
import math
from copy import deepcopy
from datetime import timezone

import pytest
from sqlalchemy.orm import sessionmaker

from app.design import service
from app.design.brief import merge_facts, mock_extract, validate_fact
from app.design.solver import _pump_layout, match_mirrors, solve_design, yvo4_index
from app.models import AgentTask, Attachment, GeneratedContent


VALUES = {
    "pump_wavelength_nm": 808, "laser_wavelength_nm": 1064, "pump_power_w": 6,
    "pump_source": "fiber", "gain_material": "Nd:YVO4", "cavity_type": "linear",
    "crystal_length_mm": 30, "active_length_mm": 18, "front_cap_mm": 6, "rear_cap_mm": 6,
    "crystal_width_mm": 3, "crystal_height_mm": 3, "doping_pct": 0.4,
    "ar_wavelengths_nm": [880, 1064, 1342, 1525], "collimator_roc_mm": 50, "focus_f_mm": 100,
}


def facts(**updates):
    return {key: {"value": value} for key, value in {**VALUES, **updates}.items()}


@pytest.fixture(scope="module")
def design():
    return solve_design(facts(), [])


def test_given_case_keeps_missing_pump_geometry_and_coating(design):
    assert design["status"] == "preliminary"
    assert design["facts"]["ar_wavelengths_nm"]["value"] == [880, 1064, 1342, 1525]
    assert any("AR@808" in issue["text"] for issue in design["issues"])
    assert design["power_prediction"]["output_w"] is None
    assert {q["key"] for q in design["questions"]} == {"fiber_core_um", "fiber_na"}
    assert "collimator_index" not in design["facts"]
    assert design["resolved_inputs"]["collimator_index"] == pytest.approx(1.51062, abs=1e-4)
    for c in design["candidates"]:
        assert c["crystal"]["thickness_mm"] == 30
        assert abs(c["m"]) < 1
        assert c["positions"][0]["z_mm"] < 0
        assert c["pump"]["status"] == "assumed_beam"
        assert c["length_mm"] > c["crystal"]["position_mm"] + 30
        assert c["bom"][0]["status"] == "purchase"


def test_cold_cavity_matches_analytic_plane_concave_slab(design):
    n, wl = yvo4_index(1064), 1064e-6
    for c in design["candidates"]:
        effective_length = c["length_mm"] - 30 + 30 / n
        zr = math.sqrt(effective_length * (c["R2_mm"] - effective_length))
        expected_waist = math.sqrt(wl * zr / math.pi)
        assert c["beam_envelope"]["points"][0]["w_mm"] == pytest.approx(expected_waist, abs=1e-6)
        center_reduced = c["crystal"]["position_mm"] + 15 / n
        center_w = expected_waist * math.sqrt(1 + (center_reduced / zr) ** 2)
        assert c["mode_radius_mm"] == pytest.approx(center_w, abs=1e-6)
        assert c["thermal_scan"][0]["m"] == pytest.approx(1 - 2 * effective_length / c["R2_mm"], abs=1e-5)


def test_output_coupling_threshold_uses_active_18mm_only(design):
    row = design["threshold_scan"][0]
    expected = -math.log(0.999 * 0.99 * 0.995) / 3.6
    assert row["required_gain_cm_inv"] == pytest.approx(expected, abs=1e-6)


def test_pump_4f_geometry_compensates_refraction():
    values = {**VALUES, "collimator_f_mm": 50, "fiber_core_um": 200, "fiber_na": 0.22}
    n = yvo4_index(808)
    layout = _pump_layout(values, 5, 20, 30, n)
    p = layout["positions"]
    assert p["collimator"] - p["source"] == pytest.approx(50)
    assert p["focus_lens"] - p["collimator"] == pytest.approx(150)
    assert 5 - p["focus_lens"] + 15 / n == pytest.approx(100)
    assert layout["image_radius_mm"] == pytest.approx(0.2)
    assert layout["collimated_radius_mm"] == pytest.approx(11)
    assert all(math.isfinite(row["w_mm"]) for row in layout["points"])


def test_corrected_focal_length_changes_pump_geometry():
    first = _pump_layout({**VALUES, "collimator_f_mm": 50, "fiber_core_um": 200, "fiber_na": 0.22}, 5, 20, 30, 2.2)
    second = _pump_layout({**VALUES, "collimator_f_mm": 100, "fiber_core_um": 200, "fiber_na": 0.22}, 5, 20, 30, 2.2)
    assert first["image_radius_mm"] == 2 * second["image_radius_mm"]
    assert first["positions"]["source"] != second["positions"]["source"]


def test_fully_specified_input_and_impossible_focus():
    result = solve_design(facts(collimator_f_mm=50, fiber_core_um=200, fiber_na=0.22), [])
    assert result["status"] == "modeled"
    assert all(p["z_mm"] is not None for p in result["candidates"][0]["positions"])
    impossible = solve_design(facts(collimator_f_mm=50, fiber_core_um=200, fiber_na=0.22, focus_f_mm=1), [])
    assert impossible["status"] == "needs_input"
    assert not impossible["candidates"]


@pytest.mark.parametrize("updates", [{"cavity_type": "ring"}, {"active_length_mm": 30}, {"max_cavity_mm": 20}])
def test_invalid_or_unsupported_geometry_does_not_fabricate_design(updates):
    result = solve_design(facts(**updates), [])
    assert result["status"] == "needs_input"
    assert not result["candidates"]
    assert any(issue["level"] == "blocking" for issue in result["issues"])


def test_r50_is_not_focal_length_and_evidence_must_exist():
    text = "R50 ,FL100,泵浦源功率最高6W,光纤输出发散光"
    extracted = mock_extract({"message": text})
    extracted["facts"] += [
        {"key": "collimator_f_mm", "value": 50, "source": "message", "quote": "R50"},
        {"key": "fiber_na", "value": 0.22, "source": "message", "quote": "NA0.22"},
    ]
    merged, _, notes = merge_facts({}, extracted, {"message": text}, [])
    assert merged["collimator_roc_mm"]["value"] == 50
    assert merged["focus_f_mm"]["value"] == 100
    assert merged["pump_power_w"]["value"] == 6
    assert "collimator_f_mm" not in merged and "fiber_na" not in merged
    assert len(notes) >= 2


def test_fact_revision_is_explicit_and_preserves_other_facts():
    extraction = {"facts": [{"key": "pump_power_w", "value": 4, "quote": "功率改为4W", "source": "message"}]}
    updated, changes, _ = merge_facts(facts(), extraction, {"message": "功率改为4W"}, [])
    assert updated["pump_power_w"]["value"] == 4
    assert updated["ar_wavelengths_nm"]["value"] == VALUES["ar_wavelengths_nm"]
    assert changes[0]["before"] == 6
    extraction["facts"][0].update(value=None, quote="撤回功率")
    updated, _, _ = merge_facts(updated, extraction, {"message": "撤回功率"}, [])
    assert "pump_power_w" not in updated


@pytest.mark.parametrize("key,value", [("fiber_na", 1.2), ("crystal_index", 1), ("pump_power_w", float("nan")), ("ar_wavelengths_nm", [808, None]), ("candidate_rank", 2.5)])
def test_invalid_numbers_rejected(key, value):
    with pytest.raises(ValueError):
        validate_fact(key, value)


def mirror(**updates):
    return {"id": 1, "name": "泵浦镜", "category": "mirror", "condition": "ok", "available_quantity": 1,
            "roc_is_flat": True, "roc_mm": None, "diameter_mm": 12.7,
            "coatings": [{"function": "HT", "wl_min_nm": 808, "wl_max_nm": 808}, {"function": "HR", "wl_min_nm": 1064, "wl_max_nm": 1064}], **updates}


def match(items, **kwargs):
    return match_mirrors(items, role="M1", roc=None, wl=1064, pump=808, min_diameter=6, **kwargs)


def test_inventory_respects_wavelength_roc_condition_and_loans():
    good = mirror()
    wrong_band = deepcopy(good)
    wrong_band["coatings"][0].update(wl_min_nm=880, wl_max_nm=880)
    result = match([good, wrong_band, mirror(available_quantity=0), mirror(condition="damaged"), mirror(roc_is_flat=False, roc_mm=100)])
    assert result["counts"] == {"matched": 1, "needs_verification": 1, "rejected": 3}
    assert "808" in result["needs_verification"][0]["unknowns"][0]


@pytest.fixture
def design_client(client, db, monkeypatch):
    monkeypatch.setattr(service, "SessionLocal", sessionmaker(bind=db.get_bind(), autoflush=False))
    return client


def test_title_only_case_defaults_and_mock_background_run(design_client):
    created = design_client.post("/api/cases", json={"title": "从需求开始"})
    assert created.status_code == 201
    cid = created.json()["id"]
    response = design_client.post(f"/api/cases/{cid}/design/runs", json={"message": "808 nm泵浦 Nd:YVO4，直线腔，1064 nm激光，最高6W，R50，FL100，光纤输出"})
    assert response.status_code == 202
    state = design_client.get(f"/api/cases/{cid}/design").json()
    assert state["runs"][0]["status"] == "completed"
    assert len(state["messages"]) == 2
    assert state["facts"]["pump_power_w"]["value"] == 6
    design = state["revisions"][0]["content"]["engineering_design"]
    assert design["status"] == "preliminary" and design["candidates"]
    assert "crystal_length_mm" not in state["facts"]  # proposed purchase, not a user fact


def test_photo_to_design_revisions_export_and_failure_preservation(design_client, db, monkeypatch, tmp_path):
    cid = design_client.post("/api/cases", json={"title": "标签设计"}).json()["id"]
    image = tmp_path / "crystal.jpg"
    image.write_bytes(b"test image handled by fake vision")
    attachment = Attachment(case_id=cid, filename="crystal.jpg", filepath=str(image))
    db.add(attachment)
    db.commit()
    aid = attachment.id

    class Vision:
        async def extract_design_facts(self, context, images):
            assert images[0]["id"] == aid and images[0]["data"]
            return {"facts": [{"key": k, "value": v, "source": f"image:{aid}", "quote": "visible label"} for k, v in VALUES.items()], "model": "vision-test"}

    monkeypatch.setattr(service, "get_ai_provider", lambda: Vision())
    response = design_client.post(f"/api/cases/{cid}/design/runs", json={"message": "请按标签设计", "attachment_ids": [aid]})
    assert response.status_code == 202
    state = design_client.get(f"/api/cases/{cid}/design").json()
    assert state["runs"][0]["status"] == "completed", state
    rid = state["revisions"][0]["id"]
    assert state["revisions"][0]["content"]["engineering_design"]["candidates"]
    for export in ["positions", "bom"]:
        downloaded = design_client.get(f"/api/cases/{cid}/design/{rid}/{export}.csv?candidate=1")
        assert downloaded.status_code == 200
        assert "M1" in downloaded.text
    assert design_client.get(f"/api/cases/{cid}/design/{rid}/positions.csv?candidate=0").status_code == 404

    class Correction:
        async def extract_design_facts(self, context, images):
            assert context["existing_facts"]["pump_power_w"]["value"] == 6
            return {"facts": [{"key": "pump_power_w", "value": 4, "source": "message", "quote": "实际最大4W"}]}

    monkeypatch.setattr(service, "get_ai_provider", lambda: Correction())
    design_client.post(f"/api/cases/{cid}/design/runs", json={"message": "实际最大4W"})
    state = design_client.get(f"/api/cases/{cid}/design").json()
    assert len(state["revisions"]) == 2
    assert state["facts"]["pump_power_w"]["value"] == 4
    assert state["revisions"][1]["content"]["engineering_design"]["facts"]["pump_power_w"]["value"] == 6

    class Failure:
        async def extract_design_facts(self, context, images):
            raise ValueError("provider error with private data")

    monkeypatch.setattr(service, "get_ai_provider", lambda: Failure())
    design_client.post(f"/api/cases/{cid}/design/runs", json={"message": "再算一次"})
    state = design_client.get(f"/api/cases/{cid}/design").json()
    assert state["runs"][0]["status"] == "failed"
    assert "private data" not in str(state)
    assert len(state["revisions"]) == 2 and state["facts"]["pump_power_w"]["value"] == 4
    assert db.query(GeneratedContent).count() == 2


def test_duplicate_run_and_foreign_attachment_rejected(design_client, db):
    cid = design_client.post("/api/cases", json={"title": "已有运行"}).json()["id"]
    assert design_client.post(f"/api/cases/{cid}/design/runs", json={"message": "  "}).status_code == 422
    assert design_client.post(f"/api/cases/{cid}/design/runs", json={"message": "设计", "attachment_ids": [12345]}).status_code == 404
    db.add(AgentTask(case_id=cid, goal="pending", mode="design", status="running"))
    db.commit()
    assert design_client.post(f"/api/cases/{cid}/design/runs", json={"message": "设计"}).status_code == 409


def test_restart_recovers_subsecond_old_task_but_keeps_accepted_run(design_client, db, monkeypatch):
    cid = design_client.post("/api/cases", json={"title": "恢复任务"}).json()["id"]
    task = AgentTask(case_id=cid, goal="pending", mode="design", status="running")
    db.add(task)
    db.commit()
    monkeypatch.setattr(service, "PROCESS_STARTED", task.created_at.replace(tzinfo=timezone.utc).timestamp() + 0.5)
    monkeypatch.setattr(service, "ACTIVE_RUNS", {task.id})
    assert design_client.get(f"/api/cases/{cid}/design").json()["runs"][0]["status"] == "running"
    service.ACTIVE_RUNS.clear()
    assert design_client.get(f"/api/cases/{cid}/design").json()["runs"][0]["status"] == "failed"


def test_distance_constraint_and_near_m1_are_hard_constraints():
    result = solve_design(facts(input_mirror_near_crystal=True, output_roc_mm=200, output_gap_mm=10), [])
    c = result['candidates'][0]
    assert c['placement']['input_gap_mm'] == 3
    assert c['placement']['output_gap_mm'] == 10
    assert c['length_mm'] == 43
    assert c['R2_mm'] == 200
    assert 'crystal_front_mm' not in result['facts']
    assert c['distance_scan']['cold_upper_exclusive_mm'] == pytest.approx(200 - 3 - 30 / yvo4_index(1064))
    assert any(row['gap_mm'] == 10 and row['stable'] for row in c['distance_scan']['rows'])
    assert any(not row['stable'] for row in c['distance_scan']['rows'])
    assert all(p['z_mm'] is not None for p in c['positions'])


def test_thermal_trace_matches_full_matrix_across_stable_and_unstable_regions():
    from app.design.solver import _thermal_stability_m
    from app.physics import beam as B
    from app.physics.design import _round_trip_with_lens
    from app.physics.toolkit import _FLAT_ROC_MM
    for front in [0, 3, 20]:
        crystal = {'position_mm': front, 'thickness_mm': 30, 'n': yvo4_index(1064)}
        for gap in [5, 50, 100, 210]:
            for roc in [50, 200, 1000]:
                for f in [None, 2000, 200, 50]:
                    length = front + 30 + gap
                    expected = B.stability(_round_trip_with_lens(length, _FLAT_ROC_MM, roc, crystal, f))['m']
                    assert _thermal_stability_m(length, roc, crystal, f) == pytest.approx(expected, abs=1e-9)


def test_fixed_pump_positions_are_preserved_and_conflicts_explained():
    n = yvo4_index(808)
    result = solve_design(facts(focus_lens_z_mm=3 - 100 + 15/n, collimator_z_mm=-240, source_z_mm=-340, collimator_f_mm=100, output_roc_mm=200, output_gap_mm=10), [])
    c = result['candidates'][0]
    assert c['crystal']['position_mm'] == pytest.approx(3)
    assert c['pump']['positions']['source'] == -340
    assert c['pump']['positions']['collimator'] == -240
    conflict = solve_design(facts(crystal_front_mm=3, collimator_z_mm=-240, source_z_mm=-320, collimator_f_mm=100, output_roc_mm=200), [])
    assert not conflict['candidates']
    assert any('固定光纤' in i['text'] for i in conflict['issues'])
    cap_focus = solve_design(facts(pump_focus_depth_mm=2), [])
    assert not cap_focus['candidates'] and any('端帽' in i['text'] for i in cap_focus['issues'])


def test_inventory_binding_locks_actual_lens_and_quantity():
    lens = {'id': 21, 'name': 'f75', 'category': 'lens', 'condition': 'ok', 'available_quantity': 1,
            'focal_length_mm': 75, 'coatings': [{'function': 'AR', 'wl_min_nm': 780, 'wl_max_nm': 850}]}
    result = solve_design(facts(collimator_inventory_id=21, output_roc_mm=200, output_gap_mm=10), [lens])
    assert result['resolved_inputs']['collimator_f_mm'] == 75
    assert result['candidates'][0]['pump']['positions']['collimator'] - result['candidates'][0]['pump']['positions']['source'] == 75
    assert result['component_bindings']['collimator']['id'] == 21
    conflict = solve_design(facts(collimator_inventory_id=21, collimator_f_mm=100), [lens])
    assert not conflict['candidates']
    doubled = solve_design(facts(collimator_inventory_id=21, focus_lens_inventory_id=21), [lens])
    assert not doubled['candidates'] and any('数量不足' in i['text'] for i in doubled['issues'])


def test_inventory_can_fill_missing_lenses_and_crystal_without_creating_facts():
    from app.design.planning import resolve_inputs
    inventory = [
        {'id': 21, 'name': 'f75', 'category': 'lens', 'condition': 'ok', 'available_quantity': 1,
         'focal_length_mm': 75, 'coatings': [{'function': 'AR', 'wl_min_nm': 780, 'wl_max_nm': 850}]},
        {'id': 22, 'name': 'f100', 'category': 'lens', 'condition': 'ok', 'available_quantity': 1,
         'focal_length_mm': 100, 'coatings': [{'function': 'AR', 'wl_min_nm': 780, 'wl_max_nm': 850}]},
        {'id': 23, 'name': 'Nd:YVO4', 'material': 'Nd:YVO4', 'category': 'gain_crystal', 'condition': 'ok',
         'available_quantity': 1, 'dimensions': '3*3*15mm3', 'coatings': []}]
    initial = {key: {'value': val} for key, val in {'gain_material': 'Nd:YVO4', 'pump_wavelength_nm': 808, 'laser_wavelength_nm': 1064}.items()}
    resolved, assumptions, issues, bindings = resolve_inputs(initial, inventory)
    assert not issues and assumptions
    assert resolved['crystal_length_mm'] == 15
    assert {bindings['collimator']['id'], bindings['focus_lens']['id']} == {21, 22}
    assert bindings['crystal']['id'] == 23
    assert len(initial) == 3


def test_nominal_fiber_image_does_not_become_measured_mode_target():
    initial = facts(fiber_core_um=9, fiber_na=.12, output_roc_mm=200, output_gap_mm=10, crystal_front_mm=3)
    initial['fiber_core_um']['verification'] = 'image_reading'
    result = solve_design(initial, [])
    assert result['optimization']['target_mode_radius_um'] == 150
    assert result['candidates'][0]['pump']['size_mismatch']
    assert result['power_prediction']['output_w'] is None


def test_rezonator_export_matches_bundled_reference_calculation(design, rezonator_reference):
    import numpy as np
    from app.design.rezonator import cold_cavity_schema
    reference = rezonator_reference
    for c in design['candidates']:
        exported = cold_cavity_schema(c, 1064)
        assert exported['trip_type'] == 'SW'
        assert exported['elements'][0]['type'] == 'ElemFlatMirror'
        # Reconstruct directly from .rez element parameters and the upstream C++
        # element definitions, without using LaserClaw's matrix constructors.
        parts = []
        for item in exported['elements'][1:-1]:
            p = item['params']
            distance = p['L']['value'] / p.get('n', {'value': 1})['value']
            parts.append(np.array([[1., distance], [0., 1.]]))
        roc = exported['elements'][-1]['params']['R']['value']
        trip = np.eye(2)
        for matrix in parts + [np.array([[1., 0.], [-2 / roc, 1.]])] + list(reversed(parts)):
            trip = matrix @ trip
        assert reference.calc_stab(trip) == pytest.approx(c['m'], abs=1e-6)
        assert reference.calc_w(trip, 1064e-6, 1) == pytest.approx(c['beam_envelope']['points'][0]['w_mm'], abs=1e-6)


def test_title_inventory_context_and_structured_constraint_roundtrip(design_client, monkeypatch):
    cid = design_client.post('/api/cases', json={'title': '808 nm泵浦 Nd:YVO4，1064 nm激光'}).json()['id']
    response = design_client.post(f'/api/cases/{cid}/design/runs', json={
        'message': '按标题开始设计', 'constraints': {'input_mirror_near_crystal': True, 'output_roc_mm': 200, 'output_gap_mm': 10}})
    assert response.status_code == 202
    state = design_client.get(f'/api/cases/{cid}/design').json()
    assert state['runs'][0]['status'] == 'completed'
    assert state['facts']['laser_wavelength_nm']['source'] == 'title'
    assert state['facts']['output_gap_mm']['verification'] == 'user_constraint'
    assert 'crystal_length_mm' not in state['facts']
    revision = state['revisions'][0]
    assert revision['content']['engineering_design']['candidates'][0]['placement']['output_gap_mm'] == 10
    exported = design_client.get(f"/api/cases/{cid}/design/{revision['id']}/cavity.rez")
    assert exported.status_code == 200
    assert exported.json()['builtin_params']['lambda']['value'] == 1064
    assert design_client.post(f'/api/cases/{cid}/design/runs', json={'message': 'bad', 'constraints': {'source_z_mm': 30}}).status_code == 422
    assert design_client.post(f'/api/cases/{cid}/design/runs', json={'message': 'bad', 'constraints': {'unknown': 1}}).status_code == 422
    design_client.post(f'/api/cases/{cid}/design/runs', json={'message': '解除固定距离', 'constraints': {'output_gap_mm': None}})
    assert 'output_gap_mm' not in design_client.get(f'/api/cases/{cid}/design').json()['facts']
