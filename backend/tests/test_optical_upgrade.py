"""Independent physical references and persisted engineering-workflow checks."""
import math
from copy import deepcopy

import numpy as np
import pytest

from app.design.solver import solve_design, yvo4_index
from app.design.analysis import analyze_design
from app.design.rezonator import cold_cavity_schema
from app.physics import beam as B
from app.physics.caustic import fit_caustic
from app.workbench.optics import analyze_system, scan_system_2d, OpticalSystem
from app.workbench.projects import SaveProject, project_from_design, read_project, save_project
from app.models import ExperimentCase


@pytest.fixture(scope="module")
def reversed_design():
    v = {"pump_wavelength_nm": 808, "laser_wavelength_nm": 1064, "pump_power_w": 6,
         "pump_source": "fiber", "gain_material": "Nd:YVO4", "cavity_type": "linear",
         "crystal_length_mm": 30, "active_length_mm": 18, "front_cap_mm": 6, "rear_cap_mm": 6,
         "crystal_width_mm": 3, "crystal_height_mm": 3, "ar_wavelengths_nm": [880, 1064, 1342, 1525],
         "collimator_roc_mm": 50, "focus_f_mm": 100, "input_mirror_near_crystal": True,
         "input_roc_mm": 200, "input_mirror_flat": False, "output_mirror_flat": True,
         "input_mirror_owned": True, "output_mirror_owned": True, "mirror_coatings_user_confirmed": True}
    return solve_design({k: {"value": x} for k, x in v.items()}, [])


def test_reversed_hardware_matches_analytic_plane_waist(reversed_design):
    d = reversed_design
    assert len(d["candidates"]) >= 3
    for c in d["candidates"]:
        assert c["R1_mm"] == 200 and c["R2_mm"] is None
        reduced = c["length_mm"]-30+30/yvo4_index(1064)
        zr = math.sqrt(reduced*(200-reduced))
        q1 = complex(-reduced, zr)
        expected = B.w_from_q(q1 + 3 + 15/yvo4_index(1064), 1064)
        assert c["mode_radius_mm"] == pytest.approx(expected, abs=1e-6)
        a = analyze_design(d, c)
        assert a["round_trip"]["determinant"] == pytest.approx(1)
        assert a["trace"]["waists"][-1]["z_mm"] == pytest.approx(c["length_mm"])
        assert c["m"] == pytest.approx(1-2*reduced/200, abs=1e-6)
        assert c["bom"][1]["transmission_pct"] is None
        assert c["bom"][0]["status"] == c["bom"][1]["status"] == "owned"
        assert c["pump"]["baseline_only"] is True


def test_reversed_export_and_engineering_project_preserve_roles(reversed_design):
    c = reversed_design["candidates"][0]
    schema = cold_cavity_schema(c, 1064)
    assert schema["elements"][0]["type"] == "ElemCurveMirror"
    assert schema["elements"][-1]["type"] == "ElemFlatMirror"
    project = project_from_design(reversed_design, c)
    general = analyze_system(project.system)
    special = analyze_design(reversed_design, c)
    assert general["planes"]["tangential"]["m"] == pytest.approx(special["stability"]["m"])
    assert general["planes"]["tangential"]["waists"][-1]["z_mm"] == pytest.approx(c["length_mm"])


def test_reversed_thermal_uses_input_mirror_curvature(reversed_design):
    c = reversed_design["candidates"][0]
    n = c["crystal"]["n"]
    elements = [{"name": "M1", "kind": "mirror", "radius_mm": 200},
                {"name": "front", "kind": "space", "length_mm": 3},
                {"name": "crystal first", "kind": "space", "length_mm": 15, "n": n},
                {"name": "thermal", "kind": "lens", "focal_mm": 100/n},
                {"name": "crystal last", "kind": "space", "length_mm": 15, "n": n},
                {"name": "tail", "kind": "space", "length_mm": c["placement"]["output_gap_mm"]},
                {"name": "M2", "kind": "mirror"}]
    general = analyze_system({"mode": "standing_wave", "wavelength_nm": 1064, "elements": elements})
    special = analyze_design(reversed_design, c, thermal_f_mm=100)
    assert general["planes"]["tangential"]["m"] == pytest.approx(special["stability"]["m"])


def test_m2_single_pass_matches_second_moment_divergence():
    out = analyze_system({"mode": "single_pass", "wavelength_nm": 808, "input_radius_mm": .1, "beam_quality_m2": 3,
                          "elements": [{"kind": "space", "name": "air", "length_mm": 100}]})
    expected = math.sqrt(.1**2+(3*808e-6*100/(math.pi*.1))**2)
    assert out["planes"]["tangential"]["output"]["radius_mm"] == pytest.approx(expected)
    with pytest.raises(ValueError, match="eigenmode"):
        OpticalSystem(mode="standing_wave", wavelength_nm=1064, beam_quality_m2=2, elements=[{"kind": "mirror", "name": "M1"}, {"kind": "space", "name": "gap", "length_mm": 10}, {"kind": "mirror", "name": "M2", "radius_mm": 200}])


def test_thick_lens_forward_and_reverse_use_physical_surface_signs():
    config = {"mode": "single_pass", "wavelength_nm": 808, "input_radius_mm": .3,
              "elements": [{"name": "lens", "kind": "thick_lens", "length_mm": 5, "n": 1.5, "front_radius_mm": 50, "back_radius_mm": -200}]}
    expected = B.interface_curved(-200, 1.5, 1) @ B.free_space(5) @ B.interface_curved(50, 1, 1.5)
    actual = analyze_system(config)["planes"]["tangential"]["matrix"]
    assert np.allclose(actual, expected)
    cavity = {"mode": "standing_wave", "wavelength_nm": 1064, "elements": [{"name": "M1", "kind": "mirror", "radius_mm": 200}, config["elements"][0], {"kind": "space", "name": "air", "length_mm": 40}, {"kind": "mirror", "name": "M2"}]}
    reverse = B.interface_curved(-50, 1.5, 1) @ B.free_space(5) @ B.interface_curved(200, 1, 1.5)
    trip = B.mirror_curved(200) @ reverse @ B.free_space(80) @ expected
    assert np.allclose(analyze_system(cavity)["planes"]["tangential"]["matrix"], trip)


def test_grin_quarter_pitch_and_custom_astigmatic_matrix():
    n, g = 1.5, .02
    length = math.pi/(2*g)
    config = {"mode": "single_pass", "wavelength_nm": 1064, "input_radius_mm": .2, "elements": [{"name": "GRIN", "kind": "grin", "n": n, "length_mm": length, "gradient_per_mm": g}]}
    m = analyze_system(config)["planes"]["tangential"]["matrix"]
    assert np.allclose(m, [[0, 1/(n*g)], [-n*g, 0]], atol=1e-12)
    config["elements"] = [{"name": "custom lens", "kind": "matrix", "matrix_t": [1, 0, -.01, 1], "matrix_s": [1, 0, -.02, 1]}, {"name": "air", "kind": "space", "length_mm": 10}]
    out = analyze_system(config)
    assert out["planes"]["tangential"]["output"]["radius_mm"] != out["planes"]["sagittal"]["output"]["radius_mm"]


def test_2d_map_matches_analytic_stability():
    system = {"mode": "standing_wave", "wavelength_nm": 1064, "elements": [{"name": "M1", "kind": "mirror", "radius_mm": 200}, {"name": "gap", "kind": "space", "length_mm": 20}, {"name": "M2", "kind": "mirror"}]}
    scan = scan_system_2d({"system": system, "x": {"element_index": 0, "parameter": "radius_mm", "start": 50, "stop": 200, "count": 4}, "y": {"element_index": 1, "parameter": "length_mm", "start": 25, "stop": 225, "count": 9}})
    for j, length in enumerate(scan["y"]):
        for i, radius in enumerate(scan["x"]):
            assert scan["maps"]["tangential"][j][i] == pytest.approx(1-2*length/radius)
            assert bool(scan["maps"]["stable_both"][j][i]) == (0 < length < radius)


def test_caustic_fit_recovers_measured_parameters_and_rejects_bad_data():
    z = np.linspace(-30, 60, 30)
    w = np.sqrt(.03**2+((z-12)*2*808e-6/(math.pi*.03))**2)
    fit = fit_caustic(z, w, 808)
    assert fit["waist_z_mm"] == pytest.approx(12)
    assert fit["waist_radius_mm"] == pytest.approx(.03)
    assert fit["m2"] == pytest.approx(2)
    with pytest.raises(ValueError):
        fit_caustic([1, 1, 1, 2, 3], [.1]*5, 808)


def test_project_history_conflicts_locks_and_reversible_edits(db, reversed_design):
    case = ExperimentCase(title="engineering", description="test", goal="test", cavity_type="linear")
    db.add(case)
    db.commit()
    p = project_from_design(reversed_design, reversed_design["candidates"][0])
    first = save_project(db, case.id, SaveProject(project=p, change_note="initial"))
    updated = deepcopy(p)
    updated.system.elements[5].length_mm += 1
    second = save_project(db, case.id, SaveProject(base_revision_id=first["revision_id"], project=updated, change_note="gap"))
    assert second["analysis"]["planes"]["tangential"]["m"] != first["analysis"]["planes"]["tangential"]["m"]
    assert read_project(db, case.id, first["revision_id"])["project"]["system"] == first["project"]["system"]
    imported = project_from_design(reversed_design, reversed_design["candidates"][0], second)
    assert imported.system.elements[0].uid == p.system.elements[0].uid
    assert imported.system.elements[3].uid == p.system.elements[3].uid
    with pytest.raises(ValueError, match="changed since"):
        save_project(db, case.id, SaveProject(base_revision_id=first["revision_id"], project=p, change_note="stale"))
    updated.system.elements[0].radius_mm = 100
    with pytest.raises(ValueError, match="Locked hardware"):
        save_project(db, case.id, SaveProject(base_revision_id=second["revision_id"], project=updated, change_note="invalid"))
    third = save_project(db, case.id, SaveProject(base_revision_id=second["revision_id"], project=p, change_note="restore"))
    assert third["analysis"] == first["analysis"]
    with pytest.raises(ValueError, match="belong"):
        read_project(db, case.id+1, first["revision_id"])


def test_project_api_persists_and_validates_scan(client, reversed_design):
    response = client.post('/api/cases', json={"title": "upgrade", "description": "test"})
    assert response.status_code in (200, 201)
    case_id = response.json()["id"]
    base = f'/api/cases/{case_id}/optical-project'
    project = project_from_design(reversed_design, reversed_design["candidates"][0]).model_dump()
    saved = client.post(base, json={"project": project, "change_note": "API acceptance"})
    assert saved.status_code == 200, saved.text
    record = saved.json()
    assert client.get(base).json()["current"]["revision_id"] == record["revision_id"]
    config = {"system": record["project"]["system"], "x": {"element_index": 1, "parameter": "length_mm", "start": 1, "stop": 5, "count": 3}, "y": {"element_index": 5, "parameter": "length_mm", "start": 5, "stop": 15, "count": 4}}
    result = client.post(base+f'/{record["revision_id"]}/scan-2d', json=config)
    assert result.status_code == 200, result.text
    assert result.json()["grid_points"] == 12
    assert client.get(base).json()["scan"] == result.json()
    second = client.post(base, json={"base_revision_id": record["revision_id"], "project": record["project"], "change_note": "new revision"}).json()
    assert second["revision_id"] != record["revision_id"]
    assert client.get(base).json()["scan"] is None
    assert client.get(base, params={"revision_id": record["revision_id"]}).json()["scan"] == result.json()
    config["system"]["elements"][0]["radius_mm"] = 99
    assert client.post(base+f'/{record["revision_id"]}/scan-2d', json=config).status_code == 422
