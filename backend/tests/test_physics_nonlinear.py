"""Phase matching: validated against published critical phase-matching angles.

Tolerances allow for Sellmeier-set scatter between published references; the
uniaxial (BBO) cases are held tight, the biaxial (LBO/KTP) principal-plane
approximation is held looser and marked medium confidence in the API.
"""
import math

from app.physics import nonlinear as NL


def test_energy_conservation_third_wavelength():
    assert abs(NL.energy_conserving_third(1064.0, 1064.0) - 532.0) < 1e-6
    l3 = NL.energy_conserving_third(1064.0, 532.0)
    assert abs(1 / l3 - (1 / 1064.0 + 1 / 532.0)) < 1e-12
    assert abs(l3 - 354.667) < 0.1


def test_bbo_shg1064_type1_angle_and_walkoff():
    pm = NL.phase_match_uniaxial("bbo", 1064.0, pm_type="I")
    assert pm.theta_deg is not None
    assert abs(pm.theta_deg - 22.8) < 0.5        # Kato: ~22.8 deg
    assert 45.0 < pm.walkoff_mrad < 70.0          # ~55-56 mrad
    assert pm.confidence == "high"
    assert abs(pm.lambda3_nm - 532.0) < 1e-6


def test_bbo_shg1064_type2_angle():
    pm = NL.phase_match_uniaxial("bbo", 1064.0, pm_type="II")
    assert abs(pm.theta_deg - 32.8) < 0.8         # ~32.8 deg


def test_bbo_thg_sfg_1064_plus_532_type1():
    pm = NL.phase_match_uniaxial("bbo", 1064.0, 532.0, pm_type="I")
    assert abs(pm.lambda3_nm - 354.667) < 0.2
    assert abs(pm.theta_deg - 31.3) < 0.8         # ~31.3 deg


def test_lbo_xy_type1_shg1064():
    pm = NL.phase_match_biaxial_plane("lbo", "xy", 1064.0, pm_type="I")
    assert pm.theta_deg == 90.0
    assert abs(pm.phi_deg - 11.5) < 1.0           # published ~11.4-11.6 deg
    assert pm.confidence == "medium"


def test_ktp_xy_type2_shg1064():
    pm = NL.phase_match_biaxial_plane("ktp", "xy", 1064.0, pm_type="II")
    assert pm.theta_deg == 90.0
    # KTP PM angle is Sellmeier-set-dependent; Fan-1987 set lands ~24-25 deg.
    assert abs(pm.phi_deg - 24.0) < 2.5


def test_unknown_crystal_raises():
    import pytest
    with pytest.raises(KeyError):
        NL.phase_match_uniaxial("quartz", 1064.0)
    with pytest.raises(KeyError):
        NL.phase_match_biaxial_plane("quartz", "xy", 1064.0)


def test_n_e_theta_bounds():
    # extraordinary index at theta=0 equals n_o; at 90 equals n_e
    n_o, n_e = 1.66, 1.54
    assert abs(NL.n_e_theta(n_o, n_e, 0.0) - n_o) < 1e-12
    assert abs(NL.n_e_theta(n_o, n_e, math.pi / 2) - n_e) < 1e-12
