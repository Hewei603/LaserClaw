"""Numerical and API regressions for the interactive, read-only analysis bench."""
import json
import math
import importlib.util
from copy import deepcopy
from pathlib import Path

import numpy as np
import pytest

from app.design.analysis import analyze_design, probe_design
from app.design.solver import solve_design
from app.models import AgentTask, ExperimentCase, GeneratedContent


@pytest.fixture(scope="module")
def optical_design():
    values = dict(pump_wavelength_nm=808, laser_wavelength_nm=1064, pump_power_w=6,
                  pump_source="fiber", gain_material="Nd:YVO4", cavity_type="linear",
                  crystal_length_mm=30, active_length_mm=18, front_cap_mm=6, rear_cap_mm=6,
                  crystal_width_mm=3, crystal_height_mm=3, doping_pct=.4,
                  ar_wavelengths_nm=[880, 1064, 1342, 1525], collimator_roc_mm=50,
                  focus_f_mm=100, fiber_core_um=9, input_mirror_near_crystal=True,
                  output_roc_mm=200, output_gap_mm=7)
    return solve_design({k: {"value": v} for k, v in values.items()}, [])


@pytest.mark.parametrize("z", [0, 2.987654321, 3, 12.3456789123, 33, 39.87654321, 40])
def test_exact_probe_matches_analytic_slab_cavity(optical_design, z):
    c = optical_design["candidates"][0]
    n = c["crystal"]["n"]
    reduced_length = 3 + 30 / n + 7
    zr = math.sqrt(reduced_length * (200 - reduced_length))
    reduced_z = z if z < 3 else 3 + min(z - 3, 30) / n + max(0, z - 33)
    local_n = n if 3 <= z < 33 else 1
    p = probe_design(optical_design, c, z_mm=z)["point"]
    expected_w = math.sqrt(1064e-6 * zr / math.pi) * math.sqrt(1 + (reduced_z / zr) ** 2)
    assert p["w_mm"] == pytest.approx(expected_w, rel=1e-11)
    assert p["q_real_mm"] == pytest.approx(reduced_z * local_n, abs=1e-10)
    assert p["q_imag_mm"] == pytest.approx(zr * local_n, rel=1e-11)
    assert p["n"] == local_n


def test_boundaries_keep_continuous_width_and_refracted_wavefront(optical_design):
    c = optical_design["candidates"][0]
    a = analyze_design(optical_design, c)
    for z in [3, 33]:
        b = next(b for b in a["boundaries"] if b["z_mm"] == z)
        before, after = b["before"], b["after"]
        assert before["w_mm"] == pytest.approx(after["w_mm"], rel=1e-13)
        assert after["R_mm"] / before["R_mm"] == pytest.approx(after["n"] / before["n"], rel=1e-13)
        sides = [p for p in a["trace"]["points"] if p["z_mm"] == z]
        assert len(sides) == 2
        assert sides[0]["n"] != sides[1]["n"]
    waist = a["trace"]["waists"][0]
    assert waist["z_mm"] == pytest.approx(0, abs=1e-10)
    assert waist["R_mm"] is None
    assert waist["z_R_mm"] == pytest.approx(math.pi * waist["w_mm"] ** 2 / 1064e-6)
    assert waist["divergence_half_mrad"] == pytest.approx(1064e-3 / math.pi / waist["w_mm"])
    assert a["round_trip"]["determinant"] == pytest.approx(1)
    json.dumps(a, allow_nan=False)


@pytest.mark.parametrize("heat", [50, 100, 500])
def test_hot_cavity_is_self_consistent_and_lens_jump_is_physical(optical_design, heat):
    c = optical_design["candidates"][0]
    a = analyze_design(optical_design, c, thermal_f_mm=heat)
    assert a["stability"]["stable"]
    m = a["round_trip"]
    start = a["trace"]["points"][0]
    q = complex(start["q_real_mm"], start["q_imag_mm"])
    assert (m["A"] * q + m["B_mm"]) / (m["C_per_mm"] * q + m["D"]) == pytest.approx(q, rel=1e-10)
    assert a["trace"]["points"][-1]["R_mm"] == pytest.approx(200, rel=1e-12)
    lens = next(b for b in a["boundaries"] if b["z_mm"] == 18)
    assert lens["before"]["w_mm"] == pytest.approx(lens["after"]["w_mm"])
    assert lens["after"]["inverse_R_per_mm"] - lens["before"]["inverse_R_per_mm"] == pytest.approx(-1 / heat)
    assert probe_design(optical_design, c, z_mm=18, thermal_f_mm=heat)["point"]["inverse_R_per_mm"] == lens["after"]["inverse_R_per_mm"]
    assert a["cold_reference"]["points"][0]["w_mm"] > start["w_mm"]
    json.dumps(a, allow_nan=False)


def test_unstable_distance_has_no_fabricated_mode_or_clamped_scan(optical_design):
    c = optical_design["candidates"][0]
    a = analyze_design(optical_design, c, output_gap_mm=210)
    assert not a["stability"]["stable"]
    assert not a["trace"]["points"] and not a["boundaries"]
    assert probe_design(optical_design, c, z_mm=18, output_gap_mm=210)["point"] is None
    assert any(abs(p["m"]) > 1.5 for s in a["scan"]["series"] for p in s["points"])
    # Every distance scan uses the same matrix physics, including the selected gap.
    for s in a["scan"]["series"]:
        point = next(p for p in s["points"] if p["gap_mm"] == 210)
        computed = analyze_design(optical_design, c, output_gap_mm=210, thermal_f_mm=s["f_mm"], samples=100, scan_samples=100)
        assert point["m"] == pytest.approx(computed["stability"]["m"], abs=1e-11)


@pytest.mark.parametrize("samples", [100, 900, 2400])
def test_submillimetre_pump_waist_is_resolved_at_every_density(optical_design, samples):
    c = optical_design["candidates"][0]
    a = analyze_design(optical_design, c, mode="pump", samples=samples)
    focused = [p for p in a["trace"]["waists"] if 3 <= p["z_mm"] <= 33]
    assert len(focused) == 1
    waist = focused[0]
    expected = .0045 * c["pump"]["focus_f_mm"] / c["pump"]["collimator_f_mm"]
    assert waist["z_mm"] == pytest.approx(18, abs=1e-10)
    assert waist["w_mm"] == pytest.approx(expected, rel=1e-12)
    assert waist["R_mm"] is None
    assert min(p["w_mm"] for p in a["trace"]["points"] if 3 <= p["z_mm"] <= 33) == pytest.approx(expected, rel=1e-12)
    p = probe_design(optical_design, c, mode="pump", z_mm=18)["point"]
    assert p["R_mm"] is None and p["w_mm"] == pytest.approx(expected)
    assert probe_design(optical_design, c, mode="pump", z_mm=33)["point"]["n"] > 2
    assert a["estimated_M2"] == pytest.approx(math.pi * .0045 * .12 / 808e-6)
    json.dumps(a, allow_nan=False)


def test_probe_is_independent_of_plot_sampling_and_rejects_outside(optical_design):
    c = optical_design["candidates"][0]
    point = probe_design(optical_design, c, z_mm=12.3456789123)
    for count in [100, 2400]:
        a = analyze_design(optical_design, c, samples=count)
        assert not any(p["z_mm"] == 12.3456789123 for p in a["trace"]["points"])
        assert probe_design(optical_design, c, z_mm=12.3456789123) == point
    for z in [-.01, 40.01]:
        with pytest.raises(ValueError, match="范围"):
            probe_design(optical_design, c, z_mm=z)


@pytest.fixture
def saved_analysis(client, db, optical_design):
    cid = client.post('/api/cases', json={"title": "数值分析不会修改设计"}).json()["id"]
    artifact = GeneratedContent(case_id=cid, content_type="plan", content={"engineering_design": optical_design})
    db.add(artifact)
    db.commit()
    return cid, artifact.id


def test_analysis_api_is_read_only_and_rejects_invalid_requests(client, db, saved_analysis, monkeypatch):
    from app.design import service
    def forbidden(*args, **kwargs):
        pytest.fail("Read-only analysis must not invoke the design agent")
    monkeypatch.setattr(service, "execute_design", forbidden)
    cid, aid = saved_analysis
    original = deepcopy(db.get(GeneratedContent, aid).content)
    facts = deepcopy(db.get(ExperimentCase, cid).parameters)
    base = f"/api/cases/{cid}/design/{aid}"
    a = client.post(base + '/analysis', json={"output_gap_mm": 12.3, "thermal_f_mm": 100})
    assert a.status_code == 200
    assert a.json()["output_gap_mm"] == 12.3
    assert client.post(base + '/probe', json={"z_mm": 12.3456789123}).status_code == 200
    for body in [{"samples": 10}, {"samples": 5001}, {"output_gap_mm": 0}, {"output_gap_mm": 2001}, {"output_gap_mm": "NaN"}, {"thermal_f_mm": "inf"}, {"mode": "fake"}]:
        assert client.post(base + '/analysis', json=body).status_code == 422
    assert client.post(base + '/probe', json={"z_mm": 40.01}).status_code == 422
    assert client.post(base + '/probe', json={"z_mm": "NaN"}).status_code == 422
    assert client.post(base + '/analysis', json={"candidate": 5}).status_code == 404
    other = client.post('/api/cases', json={"title": "另一案例"}).json()["id"]
    assert client.post(f"/api/cases/{other}/design/{aid}/analysis", json={}).status_code == 404
    db.expire_all()
    assert db.query(GeneratedContent).count() == 1 and db.query(AgentTask).count() == 0
    assert db.get(GeneratedContent, aid).content == original
    assert db.get(ExperimentCase, cid).parameters == facts


def test_cold_scan_boundary_matches_closed_form(optical_design):
    c = optical_design["candidates"][0]
    a = analyze_design(optical_design, c)
    upper = 200 - 3 - 30 / c["crystal"]["n"]
    assert a["scan"]["cold_upper_exclusive_mm"] == pytest.approx(upper)
    cold = a["scan"]["series"][0]
    assert np.array([p["m"] for p in cold["points"]]) == pytest.approx([1 - 2 * (3 + 30 / c["crystal"]["n"] + p["gap_mm"]) / 200 for p in cold["points"]])


@pytest.mark.parametrize("heat", [None, 100, 500])
def test_piecewise_probe_matches_rezonator_reference(optical_design, heat):
    """Independent element products; compare at each physical reference plane.

    Beam width uses the bundled upstream Python helper. Curvature uses the
    closed form in Rezonator src/math/AbcdCalculator.cpp (not a C++ execution).
    """
    path = Path(__file__).resolve().parents[2] / 'rezonator2-master/calc/rezonator.py'
    spec = importlib.util.spec_from_file_location('rezonator_analysis_reference', path)
    reference = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(reference)
    c = optical_design["candidates"][0]
    n = c["crystal"]["n"]
    def space(d):
        return np.array([[1., d], [0., 1.]])
    enter, leave = np.diag([1., 1 / n]), np.diag([1., n])
    lens = np.array([[1., 0.], [-1 / heat if heat else 0., 1.]])
    forward = [space(3), enter, space(15), lens, space(15), leave, space(7)]
    backward = [space(7), enter, space(15), lens, space(15), leave, space(3)]
    trip = np.eye(2)
    for m in forward + [np.array([[1., 0.], [-2 / 200, 1.]])] + backward:
        trip = m @ trip
    for z in [0, 2.987654, 3, 12.345678, 18, 27, 33, 37.5, 40]:
        transfer = np.eye(2)
        previous = 0
        for boundary, element in [(3, enter), (18, lens), (33, leave)]:
            if boundary <= z:
                transfer = element @ space(boundary - previous) @ transfer
                previous = boundary
        transfer = space(z - previous) @ transfer
        local = transfer @ trip @ np.linalg.inv(transfer)
        point = probe_design(optical_design, c, z_mm=z, thermal_f_mm=heat)["point"]
        assert point["w_mm"] == pytest.approx(reference.calc_w(local, 1064e-6, point["n"]), rel=1e-10)
        inverse_r = (local[1, 1] - local[0, 0]) / (2 * local[0, 1])
        assert point["inverse_R_per_mm"] == pytest.approx(inverse_r, abs=1e-13)
