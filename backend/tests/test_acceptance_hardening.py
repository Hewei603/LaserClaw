"""Regression tests for defects found by the acceptance adversarial review.

Every test here pins a confirmed finding whose repro came from an independent
reviewer, so the author-written happy-path tests cannot mask a reopening.
"""
import io
import os
import tempfile

import numpy as np
import openpyxl
import pytest

from app.api.case_modules import _load_xy_csv
from app.inventory.evaluator import _dominates, evaluate_item
from app.inventory.parser import parse_coating
from app.physics.laser_metrics import caird, findlay_clay, fit_power_curve

REVIEWER = {"x-user-role": "reviewer", "x-user-id": "98"}


# --- laser metrics ----------------------------------------------------------

def test_spurious_collinear_tail_does_not_hijack_fit():
    """A collinear high-pump tail must not capture the fit (was: thr 4.0 vs true 2.0)."""
    pump = [0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11]
    output = [0.0, 0.01, 0.0, 0.41, 0.79, 1.20, 1.62, 1.99, 2.4, 3.0, 3.6, 4.2]
    fit = fit_power_curve(pump, output)
    assert fit["status"] == "completed"
    assert fit["threshold_pump"] < 3.0, "tail-only fit reopened"
    assert fit["points_in_fit"] >= 8, "fit must span the real linear region"
    assert fit["warnings"], "a kinked two-slope curve must not pass silently"


def test_pure_noise_never_returns_silently():
    """No threshold in the data => never an empty warnings list."""
    silent = 0
    for seed in range(300):
        rng = np.random.default_rng(seed)
        fit = fit_power_curve(list(np.linspace(0, 10, 13)),
                              list(np.abs(rng.normal(0, 1, 13))))
        if fit.get("status") == "completed" and not fit["warnings"]:
            silent += 1
    assert silent == 0, f"{silent} noise fits returned with no warning"


def test_slope_consistency_warning_only_on_kinked_data():
    pump = list(np.linspace(0, 14, 17))
    clean = fit_power_curve(pump, [max(0.0, 0.4 * (p - 2.0)) for p in pump])
    assert clean["warnings"] == []
    assert abs(clean["threshold_pump"] - 2.0) < 0.05
    assert abs(clean["slope_efficiency"] - 0.4) < 0.01


def test_caird_handles_zero_output_coupler():
    """T=0 (no output coupling) must be skipped, not divide by zero."""
    result = caird([{"output_coupler_T_pct": 0, "slope_efficiency": 0.10},
                    {"output_coupler_T_pct": 5, "slope_efficiency": 0.40}])
    assert result is None or result.get("applicable") in (True, False)


def test_loss_analyses_tolerate_string_typed_transmission():
    result = findlay_clay([{"output_coupler_T_pct": "5", "threshold_pump": 3.0},
                           {"output_coupler_T_pct": 10, "threshold_pump": 5.0}])
    assert result is None or "round_trip_loss_pct" in result


def test_two_point_loss_fit_carries_caveat():
    result = findlay_clay([{"output_coupler_T_pct": 2, "threshold_pump": 3.0},
                           {"output_coupler_T_pct": 10, "threshold_pump": 5.0}])
    assert result["r_squared"] == 1.0
    assert "warning" in result, "a 2-point fit must not look maximally trustworthy"


# --- evaluator --------------------------------------------------------------

class _Band:
    def __init__(self, surface, lo, hi, fn, vt=None, cmp=None, val=None):
        self.surface, self.wl_min_nm, self.wl_max_nm, self.function = surface, lo, hi, fn
        self.value_type, self.comparator, self.value_pct = vt, cmp, val


class _Item:
    def __init__(self, coatings, roc=None, flat=False, diameter=None, quantity=1.0):
        self.id, self.name, self.category = 1, "t", "mirror"
        self.coatings, self.roc_mm, self.roc_is_flat = coatings, roc, flat
        self.diameter_mm, self.dimensions, self.location = diameter, None, None
        self.quantity, self.condition = quantity, "ok"
        self.parse_confidence, self.raw_spec = "parsed", "raw"


def test_known_reflectivity_below_spec_is_vetoed():
    """An HR labelled R=85% must never be an eligible design_match for R>=99.5%."""
    verdict = evaluate_item(
        _Item([_Band("S1", 1064, 1064, "HR", "R", "=", 85.0)]),
        {"surfaces": [{"wavelength_nm": 1064, "function": "HR", "min_R_pct": 99.5}]},
    )
    assert verdict["parameters"]["coatings"][0]["status"] == "below_spec"
    assert verdict["hard_violations"]
    assert verdict["eligible"] is False


def test_anti_reflection_threshold_not_accepted_as_reflector():
    """`R<0.2%` is an AR spec — the physical opposite of a mirror."""
    parsed = parse_coating("S1:1064 R<0.2%", "S1")
    verdict = evaluate_item(_Item(parsed.bands),
                            {"surfaces": [{"wavelength_nm": 1064, "function": "HR"}]})
    assert verdict["parameters"]["coatings"][0]["status"] != "design_match"
    assert verdict["eligible"] is False


def test_explicit_conflict_beats_archetype_guess():
    """An explicit HT@1064 outranks a maybe_usable inferred from HR@1123."""
    verdict = evaluate_item(
        _Item([_Band("S1", 1123, 1123, "HR"), _Band("S1", 1064, 1064, "HT", "T", ">", 90.0)], flat=True),
        {"surfaces": [{"wavelength_nm": 1064, "function": "HR"}], "roc_mm": "flat"},
    )
    assert verdict["parameters"]["coatings"][0]["status"] == "conflict"
    assert verdict["eligible"] is False


def test_spec_failing_candidate_never_dominates_compliant_one():
    req = {"surfaces": [{"wavelength_nm": 1064, "function": "HR", "min_R_pct": 99.5}],
           "roc_mm": 400, "roc_tol_pct": 3}
    compliant = evaluate_item(_Item([_Band("S1", 1064, 1064, "HR", "R", ">", 99.6)], roc=406), req)
    failing = evaluate_item(_Item([_Band("S1", 1064, 1064, "HR", "R", "=", 85.0)], roc=400), req)
    assert not _dominates(failing, compliant)


def test_trailing_bare_wavelengths_are_not_silently_dropped():
    parsed = parse_coating("S1:AR@1064 1053 1047", "S1")
    kept = sorted(b.wl_min_nm for b in parsed.bands)
    assert kept == [1047.0, 1053.0, 1064.0] or parsed.confidence != "parsed"


# --- importer ---------------------------------------------------------------

def _workbook_bytes():
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.append(["序号", "物料名称", "S1", "S2", "规格", "曲率", "数量", "存放地", "保管人", "厂商"])
    ws.append([1, "1064腔镜", "S1:1064HR", "", "D=25mm", "R=-400", 2, "127", "a", "v"])
    ws.append([None] * 10)                                          # interior blank row
    ws.append([2, "另一片", "S1:532AR", "", "D=25mm", "平镜", 0, "127", "a", "v"])  # qty 0
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def test_blank_rows_and_zero_quantity(client):
    resp = client.post(
        "/api/inventory/import",
        files={"file": ("hardening.xlsx", _workbook_bytes(),
                        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
        headers=REVIEWER,
    )
    assert resp.status_code == 200, resp.text
    report = resp.json()
    assert report["imported"] == 2, "interior blank row imported as a phantom item"
    assert report["skipped_empty"] == 1
    items = client.get("/api/inventory/items").json()
    assert 0.0 in [i["quantity"] for i in items], "a real stock quantity of 0 was rewritten"


def test_import_rejects_oversized_upload(client, monkeypatch):
    from app.api import inventory as inventory_api

    monkeypatch.setattr(inventory_api.settings, "max_upload_size", 10)
    resp = client.post(
        "/api/inventory/import",
        files={"file": ("big.xlsx", _workbook_bytes(),
                        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
        headers=REVIEWER,
    )
    assert resp.status_code == 413


# --- power curve wiring -----------------------------------------------------

@pytest.mark.parametrize("ext,content", [
    (".txt", "0 0\n1 0\n2 0.4\n3 0.8\n"),
    (".tsv", "0\t0\n1\t0\n2\t0.4\n3\t0.8\n"),
    (".csv", "0,0\n1,0\n2,0.4\n3,0.8\n"),
])
def test_data_loader_accepts_every_advertised_format(ext, content):
    path = os.path.join(tempfile.gettempdir(), f"laserclaw_pc_test{ext}")
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(content)
    loaded = _load_xy_csv(path)
    assert loaded is not None, f"{ext} upload failed to parse"
    assert len(loaded[0]) == 4


def test_component_match_survives_non_dict_requirement(client):
    """parameters.component_requirement = null must not 500 the direct-run path."""
    case = client.post("/api/cases", json={
        "title": "bad req", "cavity_type": "linear", "goal": "g",
        "parameters": {"component_requirement": None},
    })
    case_id = case.json()["id"]
    module = client.post(f"/api/cases/{case_id}/modules",
                         json={"module_type": "component_match"}).json()
    run = client.post(f"/api/cases/modules/{module['id']}/run", json={"config_json": {}})
    assert run.status_code == 200, run.text


def test_zero_transmission_series_does_not_crash_run(client):
    """A T=0 tag on one series must not 500 the second run via caird()."""
    case_id = client.post("/api/cases", json={
        "title": "T0", "cavity_type": "linear", "goal": "g",
    }).json()["id"]
    pump = list(np.linspace(0, 8, 11))
    data = {"pump": pump, "output": [max(0.0, 0.4 * (p - 2.0)) for p in pump]}
    for t_pct in (0, 5):
        module = client.post(f"/api/cases/{case_id}/modules", json={
            "module_type": "power_curve",
            "config_json": {"output_coupler_T_pct": t_pct, "data": data},
        }).json()
        run = client.post(f"/api/cases/modules/{module['id']}/run", json={"config_json": {}})
        assert run.status_code == 200, run.text
        assert run.json()["result_json"]["status"] == "completed"
