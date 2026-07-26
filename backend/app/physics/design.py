"""Cavity DESIGN search — find a workable geometry when the user has not given one.

The common real case is that a user says "I want 1064 nm out of an 808 nm-pumped
Nd:YAG" and supplies no mirror radii at all.  Analysing a geometry they never
chose is useless; what they need is for LaserClaw to *search* for a geometry
that works and hand back concrete, buildable numbers.

:func:`design_linear_cavity` sweeps candidate mirror pairs x cavity lengths,
keeps only physically valid configurations, and ranks the survivors by an
explicit, auditable objective (mode match, stability robustness, crystal fit).
Every returned candidate carries the score breakdown, so a reviewer can see WHY
it won rather than trusting a black box.

Preferring radii the lab actually owns is the whole point of passing
``candidate_rocs`` from the structured inventory: a perfect design built from
mirrors nobody has is worthless.
"""
from __future__ import annotations

import math
from typing import Any

from .toolkit import _FLAT_ROC_MM, _analyze_length

# Catalogue radii to fall back on when the lab inventory is unknown. These are
# stock values most optics vendors carry, so a suggestion stays purchasable.
DEFAULT_CANDIDATE_ROCS: tuple[Any, ...] = (
    "flat", 50.0, 75.0, 100.0, 150.0, 200.0, 250.0, 300.0, 400.0, 500.0, 750.0, 1000.0,
)

# A cavity sitting at |m| ~ 1 is on the edge of the stability zone: a small
# thermal lens or misalignment drops it out. Keep a margin.
_MAX_ABS_M = 0.85
# Reject absurd spot sizes (mm) that no ordinary 1/2" optic supports.
_MAX_SPOT_MM = 2.0


def _roc_value(roc: Any) -> float:
    return _FLAT_ROC_MM if roc == "flat" else float(roc)


def _score(candidate: dict, target_waist_mm: float | None) -> tuple[float, dict]:
    """Lower is better. Returns (score, breakdown) so the ranking is explainable."""
    abs_m = abs(candidate["stability_m"])
    # Robustness: distance from the stability edge, normalised to 0..1.
    edge_penalty = abs_m / _MAX_ABS_M

    breakdown = {"stability_edge_penalty": round(edge_penalty, 4), "abs_m": round(abs_m, 4)}
    score = 0.45 * edge_penalty

    if target_waist_mm:
        w0 = candidate.get("waist_w0_mm") or 0.0
        waist_err = abs(w0 - target_waist_mm) / target_waist_mm if w0 else 1.0
        breakdown["waist_relative_error"] = round(waist_err, 4)
        score += 0.55 * min(waist_err, 1.0)
    else:
        # No target: prefer a waist that is neither diffraction-tiny nor huge,
        # which keeps intensity sane for a typical end-pumped rod.
        w0 = candidate.get("waist_w0_mm") or 0.0
        comfort = abs(math.log10(w0 / 0.25)) if w0 > 0 else 1.0
        breakdown["waist_comfort_penalty"] = round(comfort, 4)
        score += 0.55 * min(comfort, 1.0)

    return score, breakdown


def design_linear_cavity(
    *,
    wavelength_nm: float = 1064.0,
    crystal: dict | None = None,
    target_waist_mm: float | None = None,
    candidate_rocs: list | tuple | None = None,
    max_length_mm: float = 800.0,
    length_step_mm: float = 5.0,
    top_n: int = 3,
) -> dict[str, Any]:
    """Search mirror pairs x cavity length for a workable linear cavity.

    Returns ``{"status", "candidates": [...], "search_space": {...},
    "objective": str, "caveats": [...]}``.  ``candidates`` are ranked best-first
    and each carries the full geometry plus the score breakdown.
    """
    rocs = list(candidate_rocs) if candidate_rocs else list(DEFAULT_CANDIDATE_ROCS)
    if not rocs:
        rocs = list(DEFAULT_CANDIDATE_ROCS)

    evaluated = 0
    stable_found = 0
    best_per_pair: dict[tuple, dict] = {}

    for i, r1 in enumerate(rocs):
        for r2 in rocs[i:]:  # symmetric: (A,B) covers (B,A) for a linear cavity
            if r1 == "flat" and r2 == "flat":
                continue  # plane-parallel is marginally stable at best
            r1v, r2v = _roc_value(r1), _roc_value(r2)
            length = 20.0
            while length <= max_length_mm:
                evaluated += 1
                try:
                    analysis = _analyze_length(length, r1v, r2v, wavelength_nm, crystal)
                except ValueError:
                    length += length_step_mm
                    continue  # crystal does not fit at this length
                if analysis.get("stable") and analysis.get("waist_w0_mm"):
                    abs_m = abs(analysis["stability_m"])
                    spot_max = max(
                        analysis.get("w_on_mirror1_mm") or 0.0,
                        analysis.get("w_on_mirror2_mm") or 0.0,
                    )
                    if abs_m <= _MAX_ABS_M and spot_max <= _MAX_SPOT_MM:
                        stable_found += 1
                        cand = {
                            "crystal": crystal,
                            "R1_mm": None if r1 == "flat" else r1v,
                            "R2_mm": None if r2 == "flat" else r2v,
                            "R1_label": "flat" if r1 == "flat" else f"R={r1v:g}mm",
                            "R2_label": "flat" if r2 == "flat" else f"R={r2v:g}mm",
                            **analysis,
                        }
                        score, breakdown = _score(cand, target_waist_mm)
                        cand["score"] = round(score, 5)
                        cand["score_breakdown"] = breakdown
                        key = (r1, r2)
                        if key not in best_per_pair or score < best_per_pair[key]["score"]:
                            best_per_pair[key] = cand
                length += length_step_mm

    ranked = sorted(best_per_pair.values(), key=lambda c: c["score"])[:top_n]

    caveats = [
        "模式匹配、热透镜、泵浦光斑与增益体积的重叠未纳入本次搜索，需按推荐几何再核算。",
        "本搜索只保证腔在冷腔近轴条件下稳定且光斑合理，不代表一定能出光；"
        "阈值还取决于泵浦功率、镀膜损耗与对准质量。",
    ]
    if not ranked:
        caveats.append("在给定候选曲率与腔长范围内没有找到稳定解，请放宽范围或更换镜子。")

    return {
        "status": "completed",
        "wavelength_nm": wavelength_nm,
        "candidates": ranked,
        "search_space": {
            "candidate_rocs": [r if r == "flat" else float(r) for r in rocs],
            "roc_source": "lab inventory" if candidate_rocs else "vendor catalogue defaults",
            "length_range_mm": [20.0, max_length_mm],
            "length_step_mm": length_step_mm,
            "geometries_evaluated": evaluated,
            "stable_configurations_found": stable_found,
        },
        "objective": (
            "score = 0.45 x 稳定性边缘惩罚(|m|/0.85) + 0.55 x "
            + ("束腰相对误差" if target_waist_mm else "束腰适中度")
            + "；越小越好。硬性过滤:腔稳定、|m|<=0.85(留抗热透镜裕度)、镜面光斑<=2mm、晶体能放下。"
        ),
        "caveats": caveats,
    }
