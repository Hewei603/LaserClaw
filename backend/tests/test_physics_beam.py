"""ABCD / Gaussian beam / cavity engine: validated against analytic resonators."""
import math

import numpy as np

from app.physics import beam as B


LAM = 1064.0
LAM_MM = LAM * 1e-6


def test_free_space_and_lens_matrices():
    assert np.allclose(B.free_space(100.0), [[1, 100], [0, 1]])
    assert np.allclose(B.thin_lens(50.0), [[1, 0], [-1 / 50, 1]])
    # concave mirror R>0 -> focal length R/2
    assert np.allclose(B.mirror_curved(200.0), B.thin_lens(100.0))


def test_slab_reduces_effective_length():
    # a slab of index n, thickness t, in air -> effective length t/n
    assert np.allclose(B.slab(30.0, 1.5), [[1, 20.0], [0, 1]])


def test_q_roundtrip_beam_helpers():
    # a waist of w0 at a plane -> q = i z_R, w recovered
    w0 = 0.3
    z_r = math.pi * w0 * w0 / LAM_MM
    q = B.q_from_beam(w0, None, LAM)  # flat wavefront = waist
    assert abs(q.imag - z_r) < 1e-6
    assert abs(B.w_from_q(q, LAM) - w0) < 1e-9
    assert math.isinf(B.radius_from_q(q))


def test_symmetric_stable_cavity_matches_analytic_mirror_spot():
    R, L = 400.0, 500.0
    c = B.two_mirror_cavity(R, R, L, LAM)
    assert c["stable"]
    g = 1 - L / R
    # symmetric-cavity mirror spot: w_m^2 = (lam L / pi) / sqrt(1 - g^2)
    w_m_analytic = math.sqrt((LAM_MM * L / math.pi) / math.sqrt(1 - g * g))
    assert abs(c["w_on_mirror1_mm"] - w_m_analytic) < 1e-6
    assert abs(c["w_on_mirror1_mm"] - c["w_on_mirror2_mm"]) < 1e-9
    # waist at the centre of a symmetric cavity
    assert abs(c["waist_from_mirror1_mm"] - L / 2) < 1e-6


def test_near_confocal_waist_limit():
    # just inside the confocal boundary -> w0 -> sqrt(lam L / 2 pi)
    L = 500.0
    c = B.two_mirror_cavity(L + 1e-3, L + 1e-3, L, LAM)
    expect = math.sqrt(LAM_MM * L / (2 * math.pi))
    assert abs(c["waist_w0_mm"] - expect) / expect < 1e-3


def test_exact_confocal_is_marginal():
    c = B.two_mirror_cavity(500.0, 500.0, 500.0, LAM)
    assert c["marginal"] is True
    assert math.isnan(c["waist_w0_mm"])  # eigenmode degenerate at the boundary


def test_unstable_cavity_rejected():
    c = B.two_mirror_cavity(100.0, 100.0, 500.0, LAM)
    assert c["stable"] is False
    # round-trip eigen-q must also report no confined mode
    M = B.system_matrix([B.free_space(500.0), B.mirror_curved(100.0),
                         B.free_space(500.0), B.mirror_curved(100.0)])
    assert B.cavity_mode_q(M) is None
    assert B.stability(M)["stable"] is False


def test_eigenmode_consistent_with_two_mirror_helper():
    R1, R2, L = 300.0, 500.0, 250.0
    M = B.system_matrix([B.free_space(L), B.mirror_curved(R2), B.free_space(L), B.mirror_curved(R1)])
    q = B.cavity_mode_q(M)
    assert q is not None
    c = B.two_mirror_cavity(R1, R2, L, LAM)
    assert abs(B.w_from_q(q, LAM) - c["w_on_mirror1_mm"]) < 1e-9
