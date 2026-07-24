"""Thin-film TMM solver: validated against analytic thin-film results."""
import math

import numpy as np

from app.physics.materials import n_real
from app.physics.tmm import Layer, Stack, solve_stack, spectrum


def test_bare_interface_matches_fresnel():
    ns = n_real("fused_silica", 1064.0)
    r_fresnel = ((1 - ns) / (1 + ns)) ** 2
    res = solve_stack(Stack(layers=[], incident="air", substrate="fused_silica"), 1064.0, 0.0, "s")
    assert abs(res["R"] - r_fresnel) < 1e-9
    assert abs(res["R"] + res["T"] - 1.0) < 1e-9  # lossless


def test_ideal_quarterwave_ar_gives_zero_reflection():
    ns = n_real("fused_silica", 1064.0)
    n_ar = math.sqrt(ns)
    d = 1064.0 / (4 * n_ar)
    st = Stack(layers=[Layer(thickness_nm=d, n=n_ar)], incident="air", substrate="fused_silica")
    res = solve_stack(st, 1064.0, 0.0, "s")
    assert res["R"] < 1e-12


def test_hr_quarterwave_stack_matches_closed_form():
    nH, nL = 2.09, 1.45
    ns = n_real("fused_silica", 1064.0)
    n0 = 1.0
    N = 8
    dH, dL = 1064.0 / (4 * nH), 1064.0 / (4 * nL)
    layers = []
    for _ in range(N):
        layers += [Layer(thickness_nm=dH, n=nH), Layer(thickness_nm=dL, n=nL)]
    st = Stack(layers=layers, incident="air", substrate="fused_silica")
    res = solve_stack(st, 1064.0, 0.0, "s")
    # Equivalent-admittance closed form for (HL)^N with H incident-side, L on substrate.
    Y = (nH / nL) ** (2 * N) * ns
    R_cf = ((n0 - Y) / (n0 + Y)) ** 2
    assert abs(res["R"] - R_cf) < 1e-6
    assert res["R"] > 0.99


def test_s_equals_p_at_normal_incidence():
    st = Stack(layers=[Layer(thickness_nm=200.0, n=2.0)], incident="air", substrate="nbk7")
    res = solve_stack(st, 1064.0, 0.0, "avg")
    assert abs(res["R_s"] - res["R_p"]) < 1e-12


def test_energy_conservation_lossless():
    st = Stack(layers=[Layer(thickness_nm=133.0, n=2.09), Layer(thickness_nm=183.0, n=1.45)],
               incident="air", substrate="fused_silica")
    for aoi in (0.0, 15.0, 45.0):
        for pol in ("s", "p"):
            res = solve_stack(st, 1064.0, aoi, pol)
            assert abs(res["R"] + res["T"] + res["A"] - 1.0) < 1e-9
            assert abs(res["A"]) < 1e-9  # lossless layers -> no absorption


def test_lossy_layer_absorbs():
    # a layer with k>0 must produce A>0 and still R+T+A=1
    st = Stack(layers=[Layer(thickness_nm=500.0, n=complex(2.0, -0.05))], incident="air", substrate="fused_silica")
    res = solve_stack(st, 1064.0, 0.0, "s")
    assert res["A"] > 0.0
    assert abs(res["R"] + res["T"] + res["A"] - 1.0) < 1e-9


def test_spectrum_shape():
    st = Stack(layers=[Layer(thickness_nm=133.0, n=2.09)], incident="air", substrate="fused_silica")
    grid = np.linspace(900, 1200, 50)
    out = spectrum(st, grid, 0.0, "s")
    assert out["R"].shape == grid.shape
    assert np.all(out["R"] >= -1e-12) and np.all(out["R"] <= 1.0 + 1e-9)
