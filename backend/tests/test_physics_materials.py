"""Dispersion engine: every material reproduces its baked reference index."""
import math

import pytest

from app.physics import materials as M


def test_all_baked_check_values_match():
    data = M.load_materials()
    failures = []
    for key, entry in data.items():
        if key.startswith("_"):
            continue
        for chk, expect in (entry.get("checks") or {}).items():
            wl_um = float(chk.split("@")[1].replace("um", ""))
            got = M.n_real(key, wl_um * 1000.0)
            if abs(got - expect) >= 2e-3:
                failures.append(f"{key} {chk}: expect {expect} got {got:.4f}")
    assert not failures, "dispersion mismatches: " + "; ".join(failures)


def test_alias_resolution_case_insensitive():
    assert M.resolve_material("K9") == "nbk7"
    assert M.resolve_material("BK7") == "nbk7"
    assert M.resolve_material("Fused_Silica") == "fused_silica"


def test_unknown_material_raises():
    with pytest.raises(M.MaterialError):
        M.index_of("unobtainium", 1064.0)


def test_index_is_complex_with_loss_sign():
    # lossless materials -> zero imaginary part
    n = M.index_of("fused_silica", 1064.0)
    assert n.imag == 0.0
    assert 1.44 < n.real < 1.46


def test_index_info_reports_range_and_confidence():
    info = M.index_info("bbo_o", 800.0)  # squarely inside BBO's 0.22-1.06 um range
    assert info.in_range is True
    assert info.confidence in {"high", "medium", "representative"}
    # far outside the valid range flags out-of-range but still returns a number
    info2 = M.index_info("bbo_o", 3000.0)
    assert info2.in_range is False
    assert math.isfinite(info2.n)
