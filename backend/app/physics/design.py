"""Cavity DESIGN search — find a workable geometry when the user has not given one.

The common real case is that a user says "I want 1064 nm out of an 808 nm-pumped
Nd:YAG" and supplies no mirror radii at all.  Analysing a geometry they never
chose is useless; what they need is for LaserClaw to *search* for a geometry
that works and hand back concrete, buildable numbers.

Robustness is measured, not assumed
-----------------------------------
An earlier version of this module scored robustness with ``|m| <= 0.85``, which
is wrong: for a linear cavity ``m = 2 g1 g2 - 1``, so a small ``|m|`` only means
``g1 g2 ~ 0.5`` — true on the short-arm branch AND on the near-concentric
branch.  The near-concentric branch has a huge ``dm/d(1/f)``, so a cavity can
score perfectly and still die under a routine thermal lens (measured: R=400 mm
pair at L=685 mm scores |m|=0.016 yet goes unstable at f=1000 mm, while the same
mirrors at L=120 mm survive to f=300 mm).

So robustness is now an actual computation: :func:`thermal_lens_tolerance`
inserts a thin lens at the gain medium and sweeps its dioptric power until the
round trip leaves the stability zone.  The reported number is the thermal power
the design tolerates, which is what a lab actually cares about.

Preferring radii the lab owns is the point of ``candidate_rocs``: a perfect
design built from mirrors nobody has is worthless.
"""
from __future__ import annotations

from typing import Any

from . import beam as B
from .toolkit import _FLAT_ROC_MM, _analyze_length

# Catalogue radii to fall back on when the lab inventory is unknown. These are
# stock values most optics vendors carry, so a suggestion stays purchasable.
DEFAULT_CANDIDATE_ROCS: tuple[Any, ...] = (
    "flat", 50.0, 75.0, 100.0, 150.0, 200.0, 250.0, 300.0, 400.0, 500.0, 750.0, 1000.0,
)

# Reject absurd spot sizes (mm) that no ordinary half-inch optic supports.
_MAX_SPOT_MM = 2.0
# Thermal power (dioptres) at which we stop caring — a design that survives this
# much lensing is robust for any ordinary CW end-pumped rod.
_DIOPTRE_CEILING = 10.0
# Reference tolerance for scoring: ~5 D is f = 200 mm, a strong thermal lens.
_DIOPTRE_REFERENCE = 5.0
# Candidates carried into the (more expensive) robustness stage.
_SHORTLIST_PER_PAIR = 3
_SHORTLIST_TOTAL = 60


def _roc_value(roc: Any) -> float:
    return _FLAT_ROC_MM if roc == "flat" else float(roc)


def _round_trip_with_lens(
    length_mm: float, r1_mm: float, r2_mm: float, crystal: dict | None, f_mm: float | None,
):
    """Round-trip matrix at M1, optionally with a thermal lens in the gain medium.

    The lens sits at the centre of the crystal (or mid-cavity when no crystal is
    described) and is therefore traversed twice per round trip, as it physically
    is.
    """
    if crystal:
        n = float(crystal["n"])
        t = float(crystal["thickness_mm"])
        pos = float(crystal.get("position_mm", (length_mm - t) / 2.0))
        tail = length_mm - pos - t
        if pos < 0 or tail < 0:
            raise ValueError("crystal does not fit")
        half = [B.free_space(t / 2.0)]
        lens = [B.thin_lens(f_mm)] if f_mm else []
        forward = ([B.free_space(pos), B.interface_flat(1.0, n)] + half + lens + half
                   + [B.interface_flat(n, 1.0), B.free_space(tail)])
        backward = ([B.free_space(tail), B.interface_flat(1.0, n)] + half + lens + half
                    + [B.interface_flat(n, 1.0), B.free_space(pos)])
    else:
        half_len = [B.free_space(length_mm / 2.0)]
        lens = [B.thin_lens(f_mm)] if f_mm else []
        forward = half_len + lens + half_len
        backward = half_len + lens + half_len
    return B.system_matrix(forward + [B.mirror_curved(r2_mm)] + backward + [B.mirror_curved(r1_mm)])


def thermal_lens_tolerance(
    length_mm: float,
    r1_mm: float,
    r2_mm: float,
    crystal: dict | None,
    *,
    ceiling_dioptre: float = _DIOPTRE_CEILING,
    step_dioptre: float = 0.1,
) -> float:
    """Thermal lens power (dioptres, 1/m) the cavity tolerates before going unstable.

    Returns the largest power for which the round trip is still stable; a return
    equal to ``ceiling_dioptre`` means "tolerant beyond the tested range".
    A converging thermal lens is the dominant pump-induced perturbation in an
    end-pumped rod, so this is the practical robustness figure.
    """
    tolerated = 0.0
    power = step_dioptre
    while power <= ceiling_dioptre + 1e-9:
        f_mm = 1000.0 / power  # dioptre = 1/m -> focal length in mm
        try:
            m = B.stability(_round_trip_with_lens(length_mm, r1_mm, r2_mm, crystal, f_mm))
        except Exception:  # noqa: BLE001 - a non-physical intermediate ends the sweep
            break
        if not m["stable"]:
            break
        tolerated = power
        power += step_dioptre
    return round(tolerated, 3)


def _waist_penalty(w0: float | None, target_waist_mm: float | None) -> tuple[float, dict]:
    """Soft, non-saturating mode-size penalty so ranking never degenerates."""
    if not w0:
        return 1.0, {"waist_note": "no waist"}
    if target_waist_mm:
        err = abs(w0 - target_waist_mm) / target_waist_mm
        # err/(1+err) keeps every candidate distinguishable instead of clamping
        # everything beyond 2x the target to the same score.
        return err / (1.0 + err), {"waist_relative_error": round(err, 4)}
    # No target: mildly prefer a mode that is neither diffraction-tiny nor huge.
    ratio = w0 / 0.25
    dev = abs(ratio - 1.0) if ratio >= 1.0 else abs(1.0 / ratio - 1.0)
    return dev / (1.0 + dev), {"waist_comfort_deviation": round(dev, 4)}


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
    """Search mirror pairs x cavity length for a workable, thermally robust cavity.

    Two stages so the expensive part stays bounded: a cheap geometric sweep
    shortlists candidates by mode size, then each shortlisted geometry gets its
    thermal-lens tolerance actually computed and the final ranking combines mode
    match with measured robustness.
    """
    rocs = list(candidate_rocs) if candidate_rocs else list(DEFAULT_CANDIDATE_ROCS)
    if not rocs:
        rocs = list(DEFAULT_CANDIDATE_ROCS)

    evaluated = 0
    stable_found = 0
    shortlist: list[dict] = []

    for i, r1 in enumerate(rocs):
        # m is invariant under R1<->R2 (verified), so the upper triangle suffices.
        for r2 in rocs[i:]:
            if r1 == "flat" and r2 == "flat":
                continue  # plane-parallel is marginally stable at best
            r1v, r2v = _roc_value(r1), _roc_value(r2)
            per_pair: list[dict] = []
            length = 20.0
            while length <= max_length_mm:
                evaluated += 1
                try:
                    analysis = _analyze_length(length, r1v, r2v, wavelength_nm, crystal)
                except Exception:  # noqa: BLE001 - bad crystal dict / non-physical length
                    length += length_step_mm
                    continue
                if analysis.get("stable") and analysis.get("waist_w0_mm"):
                    spot_max = max(analysis.get("w_on_mirror1_mm") or 0.0,
                                   analysis.get("w_on_mirror2_mm") or 0.0)
                    if spot_max <= _MAX_SPOT_MM:
                        stable_found += 1
                        wp, wdet = _waist_penalty(analysis.get("waist_w0_mm"), target_waist_mm)
                        per_pair.append({
                            "crystal": crystal,
                            "R1_mm": None if r1 == "flat" else r1v,
                            "R2_mm": None if r2 == "flat" else r2v,
                            "R1_label": "flat" if r1 == "flat" else f"R={r1v:g}mm",
                            "R2_label": "flat" if r2 == "flat" else f"R={r2v:g}mm",
                            "_waist_penalty": wp,
                            "_waist_detail": wdet,
                            **analysis,
                        })
                length += length_step_mm
            # Keep several lengths per pair: the mode-matched one and the most
            # robust one are often different geometries of the SAME mirrors.
            per_pair.sort(key=lambda c: c["_waist_penalty"])
            shortlist.extend(per_pair[:_SHORTLIST_PER_PAIR])

    shortlist.sort(key=lambda c: c["_waist_penalty"])
    shortlist = shortlist[:_SHORTLIST_TOTAL]

    for cand in shortlist:
        tol = thermal_lens_tolerance(
            cand["length_mm"],
            cand["R1_mm"] if cand["R1_mm"] is not None else _FLAT_ROC_MM,
            cand["R2_mm"] if cand["R2_mm"] is not None else _FLAT_ROC_MM,
            crystal,
        )
        cand["thermal_lens_tolerance_dioptre"] = tol
        cand["thermal_lens_tolerance_min_f_mm"] = (
            None if tol <= 0 else round(1000.0 / tol, 1)
        )
        robustness_penalty = 1.0 - min(tol / _DIOPTRE_REFERENCE, 1.0)
        score = 0.55 * cand["_waist_penalty"] + 0.45 * robustness_penalty
        cand["score"] = round(score, 5)
        cand["score_breakdown"] = {
            **cand.pop("_waist_detail"),
            "waist_penalty": round(cand.pop("_waist_penalty"), 4),
            "thermal_tolerance_dioptre": tol,
            "robustness_penalty": round(robustness_penalty, 4),
            "abs_m_cold_cavity": round(abs(cand["stability_m"]), 4),
        }

    ranked = sorted(shortlist, key=lambda c: c["score"])[:top_n]

    caveats = [
        "热透镜裕度按「在增益介质处插入薄透镜」计算,是冷腔近轴判据;"
        "真实热透镜含像散与高阶项,数值仅为量级参考。",
        "泵浦光斑与基模的重叠(模式匹配)未纳入排序,需按推荐几何再核算。",
        "腔稳定且光斑合理不代表一定能出光;阈值还取决于泵浦功率、镀膜损耗与对准质量。",
    ]
    if not ranked:
        caveats.append("在给定候选曲率与腔长范围内没有找到稳定解,请放宽范围或更换镜子。")

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
            "robustness_evaluated": len(shortlist),
        },
        "objective": (
            "score = 0.55 x 模式尺寸惩罚(" + ("与目标束腰的相对偏差" if target_waist_mm else "束腰适中度")
            + ",软化不饱和) + 0.45 x 热稳健性惩罚(1 - 可承受热透镜/5 D);越小越好。"
            "硬性过滤:冷腔稳定、镜面光斑<=2mm、晶体能放下。"
            "热稳健性由「在增益介质插入薄透镜并扫描光焦度直至失稳」实测得出,"
            "不使用 |m| 作为代理(|m| 小同时出现在短臂分支与近共心分支,后者极不耐热透镜)。"
        ),
        "caveats": caveats,
    }
