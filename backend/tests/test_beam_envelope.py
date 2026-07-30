# -*- coding: utf-8 -*-
"""The layout drawing is only as trustworthy as the envelope it is drawn from.

These pin the two conventions that are easy to get silently wrong: the local
refractive index (forgetting it inflates w by sqrt(n) with no error raised) and
the difference between the reduced and the physical waist position.
"""
from app.physics import beam as B
from app.physics.toolkit import _analyze_length, _cavity_elements, beam_envelope

CRYSTAL = {"n": 1.8147, "thickness_mm": 20, "position_mm": 40}


def test_empty_cavity_waist_matches_the_analytic_solution():
    """A symmetric empty cavity has its waist at the exact centre."""
    env = beam_envelope(500.0, 1000.0, 1000.0, 1064.0, None)
    analytic = B.two_mirror_cavity(1000.0, 1000.0, 500.0, 1064.0)

    assert env["waist"]["z_mm"] == 250.0
    assert abs(env["waist"]["w0_mm"] - analytic["waist_w0_mm"]) < 1e-6


def test_samples_agree_with_trace_beam_at_element_planes():
    """The drawing and the analysis must not be able to disagree.

    Both walk the same element list, so equality here is what stops the picture
    drifting away from the numbers printed next to it.
    """
    length = 200.0
    env = beam_envelope(length, 1000.0, 1000.0, 1064.0, CRYSTAL)
    round_trip, fwd = _cavity_elements(length, 1000.0, 1000.0, CRYSTAL)
    trace = B.trace_beam(fwd, B.cavity_mode_q(B.system_matrix(round_trip)), 1064.0)

    def sampled_at(z_mm):
        return min(env["points"], key=lambda p: abs(p["z_mm"] - z_mm))["w_mm"]

    crystal_centre = next(t for t in trace if t["name"] == "crystal center")
    assert abs(sampled_at(length) - trace[-1]["w_mm"]) < 1e-5
    assert abs(sampled_at(50.0) - crystal_centre["w_mm"]) < 1e-5


def test_beam_radius_is_continuous_across_the_crystal_faces():
    """Guards the easiest silent bug: sampling the crystal with n = 1.

    w is continuous at a flat interface — only the divergence changes. Dropping
    the local index inflates w inside the crystal by sqrt(n) (~35% here) and
    raises nothing, so the drawing would simply be wrong.

    Asserted as smoothness over the whole envelope rather than by comparing the
    two samples nearest a face: the step size can place a sample exactly on the
    face, in which case "the point before" and "the point after" are the same
    point and such a check passes no matter what the code does.
    """
    env = beam_envelope(200.0, 1000.0, 1000.0, 1064.0, CRYSTAL)
    widths = [p["w_mm"] for p in env["points"]]
    mean_w = sum(widths) / len(widths)
    biggest_jump = max(abs(b - a) for a, b in zip(widths, widths[1:]))

    # A correct envelope changes by ~0.1% between neighbours; a lost index would
    # put a single ~35% discontinuity at each face.
    assert biggest_jump < 0.05 * mean_w, (
        f"discontinuity of {biggest_jump:.4f} mm against a mean radius of {mean_w:.4f} mm "
        "— the local refractive index is probably not being applied inside the crystal"
    )
    # And the samples must actually record which medium they are in.
    assert {p["n"] for p in env["points"]} == {1.0, CRYSTAL["n"]}


def test_physical_waist_position_differs_from_the_reduced_one_by_the_slab_shift():
    """`waist_from_mirror1_mm` is an optical-path length when a crystal is present.

    Using it as a drawing coordinate would misplace the waist by t(1 - 1/n) —
    here about 9 mm on a 200 mm cavity. The envelope solves Re(q) = 0 per
    segment instead, which is exact and in physical millimetres.
    """
    length = 200.0
    env = beam_envelope(length, 1000.0, 1000.0, 1064.0, CRYSTAL)
    reduced = _analyze_length(length, 1000.0, 1000.0, 1064.0, CRYSTAL)["waist_from_mirror1_mm"]

    expected_shift = CRYSTAL["thickness_mm"] * (1.0 - 1.0 / CRYSTAL["n"])
    assert abs((env["waist"]["z_mm"] - reduced) - expected_shift) < 0.01


def test_unstable_cavity_yields_no_envelope_rather_than_a_misleading_one():
    env = beam_envelope(2500.0, 1000.0, 1000.0, 1064.0, None)
    assert env["points"] == []
    assert env["waist"] is None
    assert "不稳定" in env["note"]


def test_envelope_spans_the_whole_cavity_and_declares_the_cold_cavity_caveat():
    length = 200.0
    env = beam_envelope(length, 1000.0, 1000.0, 1064.0, CRYSTAL)

    assert env["points"][0]["z_mm"] == 0.0
    assert abs(env["points"][-1]["z_mm"] - length) < 1e-6
    # The recommendation is ranked by thermal-lens margin; the picture is not.
    assert "冷腔" in env["note"]
