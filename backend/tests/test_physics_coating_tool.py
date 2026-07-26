"""Coating tool: dual-mode contract and the canonical 1123/1064 archetype case."""
import math

from app.physics.coating_tool import evaluate_coating


def test_needs_input_when_empty():
    assert evaluate_coating({})["status"] == "needs_input"


def test_exact_stack_mode_is_high_confidence():
    ns_ar = math.sqrt(1.4496)
    d = 1064.0 / (4 * ns_ar)
    req = {
        "mode": "auto",
        "query_wavelengths_nm": [1064.0],
        "stack": {"incident": "air", "substrate": "fused_silica",
                  "layers": [{"thickness_nm": d, "n": ns_ar}]},
    }
    res = evaluate_coating(req)
    assert res["status"] == "completed"
    assert res["mode_used"] == "exact_stack"
    assert res["confidence"] == "high"
    assert res["query_results"][0]["R"] < 1e-6
    assert res["query_results"][0]["is_representative_only"] is False


def test_vendor_curve_interpolates_and_nulls_outside_range():
    req = {
        "query_wavelengths_nm": [1000.0, 1500.0],
        "vendor_curve": {"wl_nm": [900, 1100, 1300], "R": [0.99, 0.995, 0.98], "source": "datasheet"},
    }
    res = evaluate_coating(req)
    assert res["mode_used"] == "vendor_curve"
    assert res["query_results"][0]["R"] is not None      # 1000 in range
    assert res["query_results"][1]["R"] is None           # 1500 out of measured range


def test_archetype_1123_hr_covers_1064():
    res = evaluate_coating({
        "nominal": {"function": "HR", "design_wavelength_nm": 1123.0},
        "query_wavelengths_nm": [1064.0],
        "aoi_deg": 0.0,
    })
    assert res["status"] == "completed"
    assert res["mode_used"] == "archetype"
    assert res["confidence"] == "low"
    assert res["recommend_measurement"] is True
    sb = res["stopband"]
    assert sb["edges_nm"][0] < 1064.0 < sb["edges_nm"][1]   # 1064 inside the stopband
    q = res["query_results"][0]
    assert q["band_position"] == "inside"
    assert q["margin_to_edge_nm"] > 0
    assert q["is_representative_only"] is True
    # honest bracket present
    assert sb["width_bracket_nm"][0] < sb["width_nm"] < sb["width_bracket_nm"][1] or \
        sb["width_bracket_nm"][0] <= sb["width_nm"] <= sb["width_bracket_nm"][1]


def test_archetype_aoi_blueshifts_center():
    res = evaluate_coating({
        "nominal": {"function": "HR", "design_wavelength_nm": 1123.0},
        "query_wavelengths_nm": [1064.0],
        "aoi_deg": 45.0,
    })
    assert res["aoi"]["center_shift_nm"] < -20.0            # blue shift is negative and sizeable
    assert res["stopband"]["edges_s_nm"] is not None
    assert res["stopband"]["edges_p_nm"] is not None


def test_archetype_far_wavelength_is_outside():
    res = evaluate_coating({
        "nominal": {"function": "HR", "design_wavelength_nm": 1064.0},
        "query_wavelengths_nm": [532.0],
    })
    q = res["query_results"][0]
    assert q["band_position"] == "outside"
    assert q["margin_to_edge_nm"] < 0                       # negative = outside the band
