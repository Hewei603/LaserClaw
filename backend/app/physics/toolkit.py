"""Workflow-facing adapters over the physics kernel.

These functions take a plain config dict and return a plain result dict using
the case-module compute convention (``status`` in ``needs_input`` | ``failed`` |
``completed``), so both the REST module runner and the Agent tool layer can call
them without duplicating logic.  Still pure: numpy + this package only.

Tools:

- :func:`run_cavity_design`  — analyze a two-mirror cavity (optionally with an
  intracavity crystal) at a fixed length, or scan the mirror spacing to find
  stable windows and recommend a length: the "where do the elements go" tool.
- :func:`run_phase_match`    — phase-matching angles / walk-off for SHG/SFG.
- :func:`run_coating_tmm`    — re-export of :func:`coating_tool.evaluate_coating`.
"""
from __future__ import annotations

from typing import Any

from . import beam as B
from . import nonlinear as NL
from .coating_tool import evaluate_coating

run_coating_tmm = evaluate_coating

_FLAT_ROC_MM = 1e15  # numerically-flat mirror


def _roc(value: Any) -> float | None:
    """Parse a mirror ROC config value: number (mm), 'flat'/'inf'/None -> flat."""
    if value is None:
        return _FLAT_ROC_MM
    if isinstance(value, str):
        v = value.strip().lower()
        if v in ("flat", "inf", "infinite", "plane", "平镜", ""):
            return _FLAT_ROC_MM
        try:
            return abs(float(v))
        except ValueError:
            return None
    try:
        return abs(float(value))
    except (TypeError, ValueError):
        return None


def _cavity_elements(l_mm: float, r2_mm: float, r1_mm: float, crystal: dict | None):
    """Forward path M1 -> M2 (+ its reverse and mirrors) as one round-trip list.

    Returns ``(round_trip_elements, forward_named)`` where ``forward_named`` is a
    list of :class:`beam.Element` used to trace spot sizes at each plane.
    """
    if not crystal:
        fwd = [B.Element("M1 -> M2", B.free_space(l_mm), 1.0)]
        rev = [B.Element("M2 -> M1", B.free_space(l_mm), 1.0)]
    else:
        n = float(crystal["n"])
        t = float(crystal["thickness_mm"])
        pos = float(crystal.get("position_mm", (l_mm - t) / 2.0))
        air2 = l_mm - pos - t
        if pos < 0 or air2 < 0:
            raise ValueError(f"crystal (position {pos} mm, thickness {t} mm) does not fit in L={l_mm} mm")
        fwd = [
            B.Element("M1 -> crystal", B.free_space(pos), 1.0),
            B.Element("crystal entrance", B.interface_flat(1.0, n), n),
            B.Element("crystal center", B.free_space(t / 2.0), n),
            B.Element("crystal second half", B.free_space(t / 2.0), n),
            B.Element("crystal exit", B.interface_flat(n, 1.0), 1.0),
            B.Element("crystal -> M2", B.free_space(air2), 1.0),
        ]
        rev = [
            B.Element("M2 -> crystal", B.free_space(air2), 1.0),
            B.Element("crystal entrance (return)", B.interface_flat(1.0, n), n),
            B.Element("crystal (return)", B.free_space(t), n),
            B.Element("crystal exit (return)", B.interface_flat(n, 1.0), 1.0),
            B.Element("crystal -> M1", B.free_space(pos), 1.0),
        ]
    round_trip = [el.M for el in fwd] + [B.mirror_curved(r2_mm)] + [el.M for el in rev] + [B.mirror_curved(r1_mm)]
    return round_trip, fwd


def _analyze_length(l_mm: float, r1_mm: float, r2_mm: float, wavelength_nm: float, crystal: dict | None) -> dict:
    """Full mode analysis of one cavity geometry.  Raises ValueError on bad geometry."""
    round_trip, fwd = _cavity_elements(l_mm, r2_mm, r1_mm, crystal)
    m_rt = B.system_matrix(round_trip)
    st = B.stability(m_rt)
    out: dict[str, Any] = {
        "length_mm": round(l_mm, 4),
        "stability_m": round(st["m"], 6),
        "stable": st["stable"],
    }
    q1 = B.cavity_mode_q(m_rt)
    if q1 is None:
        return out
    out["w_on_mirror1_mm"] = round(B.w_from_q(q1, wavelength_nm), 5)
    trace = B.trace_beam(fwd, q1, wavelength_nm)
    out["spots"] = [{"at": t["name"], "w_mm": round(t["w_mm"], 5)} for t in trace]
    out["w_on_mirror2_mm"] = round(trace[-1]["w_mm"], 5)
    w0, dist = B.waist_from_q(q1, wavelength_nm)
    out["waist_w0_mm"] = round(w0, 5)
    out["waist_position_note"] = (
        "waist size is exact; its position is measured from M1 in reduced (optical-path) "
        "units when a crystal is present" if crystal else "waist position measured from M1"
    )
    out["waist_from_mirror1_mm"] = round(dist, 3)
    if crystal:
        center = next((t for t in trace if t["name"] == "crystal center"), None)
        if center:
            out["w_in_crystal_mm"] = round(center["w_mm"], 5)
    return out


def run_cavity_design(config: dict[str, Any]) -> dict[str, Any]:
    """Analyze or design a linear two-mirror cavity.

    Config keys:
      ``wavelength_nm`` (default 1064), ``R1_mm``, ``R2_mm`` (number | 'flat'),
      one of ``L_mm`` (analyze) or ``L_scan_mm`` = {start, stop, step} (design),
      optional ``crystal`` = {n | material-free index, thickness_mm, position_mm}
      and ``target_waist_mm`` (scan recommendation criterion).
    """
    wavelength_nm = float(config.get("wavelength_nm", 1064.0))
    r1 = _roc(config.get("R1_mm"))
    r2 = _roc(config.get("R2_mm"))
    if r1 is None or r2 is None:
        return {"status": "needs_input",
                "message": "Provide R1_mm and R2_mm (radius in mm, or 'flat')."}
    crystal = config.get("crystal") or None
    if crystal and "n" not in crystal:
        return {"status": "needs_input",
                "message": "crystal config needs 'n' (refractive index) and 'thickness_mm'."}

    base = {
        "status": "completed",
        "tool": "cavity_design",
        "wavelength_nm": wavelength_nm,
        "geometry": {
            "R1_mm": None if r1 >= _FLAT_ROC_MM else r1,
            "R2_mm": None if r2 >= _FLAT_ROC_MM else r2,
            "crystal": crystal,
        },
        "assumptions": [
            "ideal aligned linear cavity, paraxial fundamental mode",
            "mirrors at normal incidence (no astigmatism)",
            "crystal modeled as a plane-parallel slab (no thermal lens unless configured)",
        ],
        "disclaimer": "Deterministic ABCD/Gaussian computation. Experimental verification required before high-power operation.",
    }

    if config.get("L_mm") is not None:
        l_mm = float(config["L_mm"])
        try:
            analysis = _analyze_length(l_mm, r1, r2, wavelength_nm, crystal)
        except ValueError as exc:
            return {"status": "failed", "message": str(exc)}
        base["analysis"] = analysis
        base["placement"] = _placement(l_mm, crystal)
        base["summary"] = _summary_line(analysis, wavelength_nm)
        return base

    scan = config.get("L_scan_mm")
    if not scan:
        return {"status": "needs_input",
                "message": "Provide L_mm (analyze one length) or L_scan_mm {start, stop, step} (design scan)."}

    start, stop = float(scan["start"]), float(scan["stop"])
    step = float(scan.get("step", max((stop - start) / 200.0, 0.1)))
    if not (stop > start and step > 0):
        return {"status": "failed", "message": "L_scan_mm requires stop > start and step > 0."}

    target = config.get("target_waist_mm")
    target = float(target) if target is not None else None

    points = []
    l_mm = start
    while l_mm <= stop + 1e-9:
        try:
            points.append(_analyze_length(l_mm, r1, r2, wavelength_nm, crystal))
        except ValueError:
            points.append({"length_mm": round(l_mm, 4), "stable": False, "stability_m": None})
        l_mm += step

    stable_pts = [p for p in points if p.get("stable") and "waist_w0_mm" in p]
    windows = _stable_windows(points)
    recommended = None
    if stable_pts:
        if target is not None:
            recommended = min(stable_pts, key=lambda p: abs(p["waist_w0_mm"] - target))
            criterion = f"waist closest to target {target} mm"
        else:
            recommended = min(stable_pts, key=lambda p: abs(p["stability_m"]))
            criterion = "maximum stability margin (|m| smallest)"
        base["recommended"] = {"criterion": criterion, **recommended}
        base["placement"] = _placement(recommended["length_mm"], crystal)

    base["scan"] = {
        "L_range_mm": [start, stop],
        "step_mm": step,
        "stable_windows_mm": windows,
        "n_points": len(points),
        # keep the table compact: at most ~60 rows for display
        "points": points[:: max(1, len(points) // 60)],
    }
    base["summary"] = (
        f"Scanned L={start}-{stop} mm: {len(windows)} stable window(s) {windows}; "
        + (f"recommended L={recommended['length_mm']} mm (w0={recommended.get('waist_w0_mm')} mm)."
           if recommended else "no stable length found — change mirror ROCs.")
    )
    if not stable_pts:
        base["status"] = "completed"
    return base


def _placement(l_mm: float, crystal: dict | None) -> list[dict[str, Any]]:
    placement = [{"element": "Mirror M1", "position_mm": 0.0}]
    if crystal:
        pos = float(crystal.get("position_mm", (l_mm - float(crystal["thickness_mm"])) / 2.0))
        placement.append({"element": "Crystal entrance", "position_mm": round(pos, 3)})
        placement.append({"element": "Crystal exit", "position_mm": round(pos + float(crystal["thickness_mm"]), 3)})
    placement.append({"element": "Mirror M2", "position_mm": round(l_mm, 3)})
    return placement


def _summary_line(analysis: dict, wavelength_nm: float) -> str:
    if not analysis.get("stable"):
        return f"Cavity UNSTABLE at L={analysis['length_mm']} mm (m={analysis.get('stability_m')})."
    return (
        f"Stable at L={analysis['length_mm']} mm (m={analysis['stability_m']}): "
        f"w0={analysis.get('waist_w0_mm')} mm, w(M1)={analysis.get('w_on_mirror1_mm')} mm, "
        f"w(M2)={analysis.get('w_on_mirror2_mm')} mm at {wavelength_nm} nm."
    )


def _stable_windows(points: list[dict]) -> list[list[float]]:
    windows: list[list[float]] = []
    open_start: float | None = None
    for p in points:
        if p.get("stable"):
            if open_start is None:
                open_start = p["length_mm"]
            last = p["length_mm"]
        else:
            if open_start is not None:
                windows.append([open_start, last])
                open_start = None
    if open_start is not None:
        windows.append([open_start, last])
    return [[round(a, 3), round(b, 3)] for a, b in windows]


def run_phase_match(config: dict[str, Any]) -> dict[str, Any]:
    """Phase-matching solve for SHG/SFG.

    Config keys: ``crystal`` (bbo|lbo|ktp|bibo), ``lambda1_nm``, optional
    ``lambda2_nm`` (SFG), ``pm_type`` ('I'|'II', default 'I'), optional
    ``planes`` for biaxial (default all three principal planes).
    """
    crystal = str(config.get("crystal", "")).strip().lower()
    if not crystal:
        return {"status": "needs_input", "message": "Provide crystal (bbo, lbo, ktp, bibo)."}
    try:
        lambda1 = float(config["lambda1_nm"])
    except (KeyError, TypeError, ValueError):
        return {"status": "needs_input", "message": "Provide lambda1_nm (fundamental wavelength in nm)."}
    lambda2 = config.get("lambda2_nm")
    lambda2 = float(lambda2) if lambda2 is not None else None
    pm_type = str(config.get("pm_type", "I")).upper()

    solutions = []
    try:
        if crystal in ("bbo",):
            pm = NL.phase_match_uniaxial(crystal, lambda1, lambda2, pm_type=pm_type)
            solutions.append(pm)
        else:
            planes = config.get("planes") or ["xy", "yz", "xz"]
            for plane in planes:
                solutions.append(NL.phase_match_biaxial_plane(crystal, plane, lambda1, lambda2, pm_type=pm_type))
    except KeyError as exc:
        return {"status": "failed", "message": str(exc)}
    except ValueError as exc:
        return {"status": "failed", "message": str(exc)}

    found = []
    for pm in solutions:
        entry = {
            "crystal": pm.crystal,
            "process": pm.process,
            "type": pm.type,
            "plane": pm.plane,
            "theta_deg": None if pm.theta_deg is None else round(pm.theta_deg, 2),
            "phi_deg": None if pm.phi_deg is None else round(pm.phi_deg, 2),
            "walkoff_mrad": None if pm.walkoff_mrad is None else round(pm.walkoff_mrad, 2),
            "lambda1_nm": pm.lambda1_nm,
            "lambda2_nm": pm.lambda2_nm,
            "lambda3_nm": round(pm.lambda3_nm, 2),
            "confidence": pm.confidence,
            "notes": pm.notes,
        }
        found.append(entry)

    matched = [f for f in found if f["theta_deg"] is not None]
    return {
        "status": "completed",
        "tool": "phase_match",
        "solutions": found,
        "matched": len(matched),
        "summary": (
            f"{len(matched)} phase-matching solution(s) for {crystal.upper()} type {pm_type} "
            f"{'SHG' if lambda2 is None else 'SFG'} at {lambda1} nm."
            if matched else
            f"No angle phase-matching solution found for {crystal.upper()} type {pm_type} in the searched planes."
        ),
        "disclaimer": (
            "Angles from bundled Sellmeier sets; biaxial results use the principal-plane "
            "approximation (confidence 'medium'). Verify the cut with the vendor before ordering."
        ),
    }
