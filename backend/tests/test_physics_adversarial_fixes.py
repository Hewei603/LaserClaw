"""Regression tests for defects found by the adversarial physics review.

Each test pins a confirmed fix so the shared code/test blind spot that hid these
(the same author wrote the original code and its tests) cannot reopen.
"""
import math

import numpy as np

from app.physics import nonlinear as NL
from app.physics.archetypes import archetype_stopband_estimate
from app.physics.coating_tool import evaluate_coating
from app.physics.materials import index_info
from app.physics.tmm import Stack, solve_RT, solve_stack


# --- TMM: lossy substrate branch (the critical one) ------------------------

def test_lossy_substrate_gives_physical_fresnel():
    # air -> (2 - 0.5i): must reproduce analytic Fresnel, never R>1 / T<0.
    R, T, A = solve_RT(np.array([], dtype=complex), np.array([], dtype=float),
                       1064.0, 0.0, "s", 1.0, complex(2.0, -0.5))
    assert abs(R - 0.13514) < 1e-4
    assert abs(T - 0.86486) < 1e-4
    assert 0.0 <= R <= 1.0 and T >= 0.0


def test_lossy_substrate_oblique_p_pol_physical():
    R, T, A = solve_RT(np.array([], dtype=complex), np.array([], dtype=float),
                       1064.0, 30.0, "p", 1.0, complex(2.0, -0.5))
    assert 0.0 <= R <= 1.0 and T >= 0.0


def test_total_internal_reflection():
    # glass (1.5) -> air (1.0) beyond the critical angle (~41.8 deg): R=1, T=0.
    R, T, A = solve_RT(np.array([], dtype=complex), np.array([], dtype=float),
                       1064.0, 50.0, "s", 1.5, 1.0)
    assert abs(R - 1.0) < 1e-9
    assert abs(T) < 1e-9


def test_grazing_incidence_p_pol_no_nan():
    res = solve_stack(Stack(layers=[], incident="air", substrate="fused_silica"), 1064.0, 90.0, "p")
    assert not math.isnan(res["R"])
    assert abs(res["R"] - 1.0) < 1e-9


# --- Archetype honesty / robustness ----------------------------------------

def test_mislabeled_high_low_not_inverted():
    # passing high/low reversed must not yield a negative-width inverted band.
    res = archetype_stopband_estimate(1064.0, function="HR",
                                      high="sio2_film", low="ta2o5_film",
                                      query_wavelengths_nm=[1064.0])
    sb = res["stopband"]
    assert sb["width_nm"] > 0
    assert sb["edges_nm"][0] < sb["edges_nm"][1]
    assert res["query_results"][0]["band_position"] == "inside"  # design wl is in its own band


def test_aoi_sp_split_is_real_not_fabricated():
    # at 45 deg the real s and p bands differ by tens of nm, not ~4 nm.
    res = archetype_stopband_estimate(1064.0, "HR", aoi_deg=45.0)
    s = res["stopband"]["edges_s_nm"]
    p = res["stopband"]["edges_p_nm"]
    assert s is not None and p is not None
    s_width = s[1] - s[0]
    p_width = p[1] - p[0]
    assert abs(s_width - p_width) > 30.0  # genuine s/p split, not a 4 nm artifact


def test_target_r_one_does_not_crash_entrypoint():
    res = evaluate_coating({"mode": "archetype",
                            "nominal": {"function": "HR", "design_wavelength_nm": 1064.0, "target_R": 1.0},
                            "query_wavelengths_nm": [1064.0]})
    assert res["status"] == "completed"


def test_vendor_curve_nan_becomes_null():
    res = evaluate_coating({"mode": "vendor_curve",
                            "vendor_curve": {"wl_nm": [1000, 1100, 1200], "R": [0.1, float("nan"), 0.9]},
                            "query_wavelengths_nm": [1050, 1150]})
    for q in res["query_results"]:
        assert q["R"] is None or math.isfinite(q["R"])  # never a bare NaN


# --- Nonlinear: multi-pairing coverage + honest no-solution ----------------

def test_bibo_shg_1064_phase_matches():
    # BiBO is a workhorse green crystal; a real principal-plane match must exist.
    solutions = [NL.phase_match_biaxial_plane("bibo", pl, 1064.0, pm_type="I")
                 for pl in ("xy", "yz", "xz")]
    matched = [s for s in solutions if s.theta_deg is not None]
    assert matched, "BiBO SHG 1064 must phase-match in at least one principal plane"
    # yz-plane Type-I lands near 11.2 deg (equiv. 168.8 deg), the published cut.
    yz = NL.phase_match_biaxial_plane("bibo", "yz", 1064.0, pm_type="I")
    assert yz.theta_deg is not None
    assert abs(yz.theta_deg - 11.2) < 1.5


def test_no_solution_returns_none_not_fake_angle():
    pm = NL.phase_match_biaxial_plane("bibo", "xy", 1064.0, pm_type="I")
    assert pm.theta_deg is None  # honest: no in-plane solution, not a plausible-looking 90 deg


def test_bbo_uniaxial_unchanged_after_refactor():
    assert abs(NL.phase_match_uniaxial("bbo", 1064.0, pm_type="I").theta_deg - 22.8) < 0.5
    assert abs(NL.phase_match_uniaxial("bbo", 1064.0, pm_type="II").theta_deg - 32.8) < 0.8


# --- Materials: honest out-of-range -----------------------------------------

def test_index_info_never_raises_out_of_range():
    info = index_info("bbo_o", 130.0)  # past the Sellmeier pole
    assert info.in_range is False
    # n may be nan, but the call must not raise and must flag the range
    info2 = index_info("ktp_z", 30000.0)
    assert info2.in_range is False
