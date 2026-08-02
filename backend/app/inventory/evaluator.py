"""L1 — deterministic per-parameter component evaluator ("the referee").

Given a REQUIREMENT SPEC for one optical role and the structured inventory,
produce a STRUCTURED VERDICT per candidate — never a single scalar score.
Each parameter is judged by a type-appropriate operator:

- continuous (ROC, diameter)          -> hard gate + numeric margin
- nominal wavelength (coating label)  -> three-state {design_match /
  maybe_usable_needs_measurement / off} using the physics stopband prior
  (:func:`app.physics.archetypes.stopband_edges`) — a label is not a curve,
  so off-design use gets an interval + category, never a fake point value
- capability family (HR vs AR/HT/PR)  -> rule compatibility, wrong family on
  the load-bearing surface is a hard violation
- descriptive text (损坏/未知...)      -> explicit unknown / must-measure flags

Hard violations veto.  Survivors are ranked by DOMINANCE: A dominates B if A is
no worse on every dimension and better on at least one; the non-dominated
frontier is what a human (or LLM judgment layer) should look at.  The LLM never
produces the physics numbers here — it only reads this output.
"""
from __future__ import annotations

from typing import Any

from sqlalchemy import func
from sqlalchemy.orm import Session, selectinload

from ..models import InventoryItem, InventoryLoan
from ..models.inventory import resolve_condition
from ..physics.archetypes import stopband_edges
from ..physics.materials import n_real

_TRANSMIT = {"AR", "HT"}
_REFLECT = {"HR"}


def available_mirror_rocs(db: Session) -> list | None:
    """Mirror radii the lab actually owns, for the cavity design search.

    A design built from mirrors nobody has is useless, so when the inventory has
    been imported the search is constrained to real stock (flat mirrors
    included). Returns None when the inventory is empty, letting the search fall
    back to a vendor catalogue.

    Mirrors only: a lens surface of radius R has f = R/(n-1), not R/2, so lens
    radii are not interchangeable cavity mirror radii — and a lens carries no HR
    coating.

    Condition is judged like everywhere else — human verdict first
    (:func:`app.models.inventory.resolve_condition`): a mirror someone marked
    broken must not seed a recommended geometry that component matching will
    then reject, and one the workbook called broken but a human cleared must.
    """
    rows = (
        db.query(InventoryItem.roc_mm, InventoryItem.roc_is_flat)
        .filter(
            InventoryItem.category == "mirror",
            func.coalesce(InventoryItem.condition_manual, InventoryItem.condition, "ok") != "damaged",
        )
        .distinct()
        .all()
    )
    rocs: list = sorted({float(r) for r, flat in rows if r and not flat})
    if any(flat for _, flat in rows):
        rocs.append("flat")
    return rocs or None

# Representative quarter-wave indices for the stopband prior (same defaults as
# the coating tool's archetype mode).
_N_HIGH = None
_N_LOW = None


def _archetype_indices(wl_nm: float) -> tuple[float, float]:
    return n_real("ta2o5_film", wl_nm), n_real("sio2_film", wl_nm)


def _coating_family(function: str) -> str:
    """Family of a *required* function label (requirements carry no thresholds)."""
    if function in _REFLECT:
        return "reflect"
    if function in _TRANSMIT:
        return "transmit"
    return "partial"


def implied_reflectivity(band) -> float | None:
    """Reflectivity (%) implied by a stored band's threshold, or None if unstated.

    ``R>99.5%`` -> 99.5 ; ``R<0.2%`` -> 0.2 (an AR spec!) ; ``T=20%`` -> ~80 ;
    ``T>90%`` -> ~10.  This is what separates a partial *reflector* from an
    anti-reflection surface written in threshold form.
    """
    if band.value_pct is None or band.value_type is None:
        return None
    value = float(band.value_pct)
    return value if band.value_type.upper() == "R" else 100.0 - value


def _band_family(band) -> str:
    """Family of a *stored* band, using its threshold when the label is ambiguous.

    A bare threshold band is parsed as ``PR``; whether it behaves as a reflector
    or as an anti-reflection surface depends entirely on the implied
    reflectivity, so classify by that instead of by the ``PR`` label.
    """
    if band.function in _REFLECT:
        return "reflect"
    if band.function in _TRANSMIT:
        return "transmit"
    implied = implied_reflectivity(band)
    if implied is None:
        return "partial"
    return "partial" if implied >= 50.0 else "transmit"


def _judge_band_against_requirement(req: dict, band, tol_nm: float = 8.0) -> dict | None:
    """Judge one stored coating band against one required band.

    Returns a status dict, or ``None`` when the band is simply irrelevant
    (different family and not covering the wavelength).
    """
    wl = float(req["wavelength_nm"])
    need_family = _coating_family(req["function"].upper())
    band_family = _band_family(band)

    covers = band.wl_min_nm - tol_nm <= wl <= band.wl_max_nm + tol_nm

    if band_family == need_family or (need_family == "reflect" and band_family == "partial"):
        if covers:
            detail = f"{band.function}@{band.wl_min_nm:g}-{band.wl_max_nm:g} 覆盖 {wl:g}nm"
            threshold_ok: bool | None = None
            if need_family == "reflect" and req.get("min_R_pct") is not None:
                implied = implied_reflectivity(band)
                if implied is not None:
                    threshold_ok = implied >= float(req["min_R_pct"])
                    if band.value_type and band.value_type.upper() == "T":
                        detail += f" (T={band.value_pct:g}% -> R≈{implied:g}%)"
            if threshold_ok is False:
                # Known reflectivity provably below the requirement: a hard fail,
                # never a design match.
                return {
                    "status": "below_spec",
                    "surface": band.surface,
                    "detail": (f"{detail};实测/标称反射率 ≈{implied_reflectivity(band):g}% "
                               f"< 需求 {float(req['min_R_pct']):g}%"),
                    "threshold_ok": False,
                    "needs_measurement": False,
                    "margin_nm": None,
                }
            return {
                "status": "design_match",
                "surface": band.surface,
                "detail": detail,
                "threshold_ok": threshold_ok,
                "needs_measurement": threshold_ok is None and req.get("min_R_pct") is not None,
                "margin_nm": round(min(wl - band.wl_min_nm, band.wl_max_nm - wl), 1),
            }
        # Off-design same-family: three-state via the physics prior.
        center = 0.5 * (band.wl_min_nm + band.wl_max_nm)
        if need_family == "reflect":
            n_h, n_l = _archetype_indices(center)
            short, long_, _ = stopband_edges(center, n_h, n_l)
            if short <= wl <= long_:
                margin = min(wl - short, long_ - wl)
                pos = "edge" if margin < 0.06 * (long_ - short) else "inside"
                return {
                    "status": "maybe_usable",
                    "surface": band.surface,
                    "detail": (f"标称 {band.function}@{center:g}nm 未覆盖 {wl:g}nm,"
                               f"但原型阻带 [{short:.0f},{long_:.0f}] 含 {wl:g} ({pos},裕度 {margin:.0f}nm)"),
                    "threshold_ok": None,
                    "needs_measurement": True,
                    "margin_nm": round(margin, 1),
                }
            return {
                "status": "off",
                "surface": band.surface,
                "detail": f"标称 {band.function}@{center:g}nm 阻带 [{short:.0f},{long_:.0f}] 不含 {wl:g}nm",
                "threshold_ok": False,
                "needs_measurement": False,
                "margin_nm": round(-min(abs(wl - short), abs(wl - long_)), 1),
            }
        # transmit family off-design: AR degrades smoothly with detune
        detune = abs(wl - center) / center
        if detune < 0.05:
            return {"status": "maybe_usable", "surface": band.surface,
                    "detail": f"标称 {band.function}@{center:g}nm,失谐 {detune:.1%} (<5%),残余反射需实测",
                    "threshold_ok": None, "needs_measurement": True, "margin_nm": None}
        if detune < 0.15:
            return {"status": "maybe_usable", "surface": band.surface,
                    "detail": f"标称 {band.function}@{center:g}nm,失谐 {detune:.1%} (边缘),建议实测",
                    "threshold_ok": None, "needs_measurement": True, "margin_nm": None}
        return {"status": "off", "surface": band.surface,
                "detail": f"标称 {band.function}@{center:g}nm,失谐 {detune:.1%},不适用",
                "threshold_ok": False, "needs_measurement": False, "margin_nm": None}

    # Opposite family covering the same wavelength on this surface = active conflict.
    if covers:
        return {
            "status": "conflict",
            "surface": band.surface,
            "detail": f"该面在 {wl:g}nm 是 {band.function}(相反功能)",
            "threshold_ok": False,
            "needs_measurement": False,
            "margin_nm": None,
        }
    return None


def _judge_coating_requirement(req: dict, item: InventoryItem) -> dict:
    """Best-surface judgement of one required coating band for an item.

    Ranking rule: EXPLICIT evidence outranks an archetype guess.  A labelled
    below-spec reflectivity or an opposite-function band at the exact required
    wavelength is hard evidence and must not be masked by a ``maybe_usable``
    that only came from the stopband prior of some other nominal line.
    """
    order = {
        "design_match": 0,   # explicit, covers, meets threshold
        "below_spec": 1,     # explicit, covers, provably fails threshold
        "conflict": 2,       # explicit opposite function at this wavelength
        "maybe_usable": 3,   # archetype prior only
        "unknown": 4,
        "off": 5,
    }
    per_surface: dict[str, list[dict]] = {"S1": [], "S2": []}
    for band in item.coatings:
        j = _judge_band_against_requirement(req, band)
        if j is not None:
            per_surface.setdefault(band.surface, []).append(j)

    best: dict | None = None
    for surface, judgments in per_surface.items():
        if not judgments:
            continue
        j = sorted(judgments, key=lambda x: order[x["status"]])[0]
        if best is None or order[j["status"]] < order[best["status"]]:
            best = j

    if best is None:
        if not item.coatings:
            need_family = _coating_family(req["function"].upper())
            if need_family == "reflect":
                return {"status": "off", "surface": None,
                        "detail": "无镀膜信息/未镀膜 — 裸面不能作反射镜", "threshold_ok": False,
                        "needs_measurement": False, "margin_nm": None}
            return {"status": "unknown", "surface": None,
                    "detail": "无镀膜信息 — 裸面透射伴 ~4%/面 Fresnel 损耗,可用性需实测",
                    "threshold_ok": None, "needs_measurement": True, "margin_nm": None}
        return {"status": "off", "surface": None,
                "detail": f"没有任何镀膜段涉及 {req['wavelength_nm']}nm/{req['function']}",
                "threshold_ok": False, "needs_measurement": False, "margin_nm": None}
    return best


def evaluate_item(item: InventoryItem, requirement: dict, loaned_qty: float = 0.0) -> dict:
    """Produce the structured verdict of one inventory item vs a requirement spec.

    ``loaned_qty`` is how much of this item is currently signed out. It defaults
    to zero so a caller with no loan context (and every existing test) evaluates
    against the full stock exactly as before.
    """
    hard: list[str] = []
    must_measure: list[str] = []
    unknowns: list[str] = []
    params: dict[str, Any] = {}

    # condition (descriptive -> flags); a human verdict outranks the parsed one.
    # getattr so the evaluator stays callable with any object carrying the L0
    # fields, not only the ORM row.
    condition = resolve_condition(item.condition, getattr(item, "condition_manual", None))
    if condition == "damaged":
        hard.append("元件标注损坏(破裂/无法维修)")
    elif condition == "uncertain":
        unknowns.append("元件状态不确定(如 切向未知/不能确定镀膜)")
        must_measure.append("确认元件实际状态")
    params["condition"] = {"status": condition,
                          "manually_marked": bool(getattr(item, "condition_manual", None))}

    # quantity — what is on the shelf, not what the workbook says the lab owns.
    # Recommending three mirrors that are all signed out is worse than
    # recommending none: the student walks to the cupboard and finds it empty.
    need_qty = float(requirement.get("quantity", 1))
    total_qty = float(item.quantity or 0)
    on_loan = float(loaned_qty or 0)
    have_qty = total_qty - on_loan
    if have_qty < need_qty:
        if on_loan > 0:
            hard.append(f"可用数量不足(需 {need_qty:g},库存 {total_qty:g},已借出 {on_loan:g})")
        else:
            hard.append(f"数量不足(需 {need_qty:g},有 {total_qty:g})")
    params["quantity"] = {"have": have_qty, "need": need_qty,
                          "total": total_qty, "on_loan": on_loan}

    # ROC (continuous, hard gate + margin)
    want_roc = requirement.get("roc_mm")
    if want_roc is not None:
        tol_pct = float(requirement.get("roc_tol_pct", 2.0))
        if want_roc == "flat":
            ok = bool(item.roc_is_flat)
            params["roc"] = {"status": "match" if ok else "mismatch", "value": "flat" if item.roc_is_flat else item.roc_mm}
            if not ok:
                hard.append("需要平镜,该件为曲面/未知曲率")
        else:
            target = float(want_roc)
            if item.roc_is_flat or item.roc_mm is None:
                params["roc"] = {"status": "mismatch", "value": "flat" if item.roc_is_flat else None, "target": target}
                if item.roc_mm is None and not item.roc_is_flat:
                    unknowns.append("曲率半径未知")
                    must_measure.append("测量曲率半径")
                    params["roc"]["status"] = "unknown"
                else:
                    hard.append(f"需要 R={target:g}mm,该件为平镜")
            else:
                dev_pct = abs(item.roc_mm - target) / target * 100.0
                status = "match" if dev_pct <= tol_pct else "mismatch"
                params["roc"] = {"status": status, "value": item.roc_mm, "target": target,
                                 "deviation_pct": round(dev_pct, 2)}
                if status == "mismatch":
                    hard.append(f"曲率 {item.roc_mm:g}mm 偏离目标 {target:g}mm ({dev_pct:.1f}% > {tol_pct}%)"
                                " — 换用此曲率需重跑腔设计")

    # diameter (continuous, hard gate + margin; unknown -> measure)
    min_d = requirement.get("min_diameter_mm")
    if min_d is not None:
        if item.diameter_mm is None:
            params["diameter"] = {"status": "unknown", "required": float(min_d)}
            unknowns.append("口径未知")
            must_measure.append("确认口径 ≥ " + str(min_d) + "mm")
        else:
            margin = item.diameter_mm - float(min_d)
            params["diameter"] = {"status": "ok" if margin >= 0 else "too_small",
                                  "value": item.diameter_mm, "required": float(min_d),
                                  "margin_mm": round(margin, 2)}
            if margin < 0:
                hard.append(f"口径 {item.diameter_mm:g}mm < 需求 {min_d}mm(切束)")

    # coating requirements (nominal-wavelength three-state per required band)
    coating_judgments = []
    for req in requirement.get("surfaces", []):
        j = _judge_coating_requirement(req, item)
        j["requirement"] = f"{req['function'].upper()}@{req['wavelength_nm']}nm" + (
            f" (R≥{req['min_R_pct']}%)" if req.get("min_R_pct") is not None else "")
        coating_judgments.append(j)
        if j["status"] in ("off", "conflict", "below_spec"):
            hard.append(f"镀膜不满足 {j['requirement']}: {j['detail']}")
        elif j["status"] == "maybe_usable":
            must_measure.append(f"实测 {j['requirement']} 处的实际 R/T({j['detail'][:40]}...)")
        elif j["status"] == "unknown":
            must_measure.append(f"实测 {j['requirement']}")
        elif j.get("needs_measurement"):
            must_measure.append(f"确认 {j['requirement']} 阈值(标称未给数值)")
    params["coatings"] = coating_judgments

    return {
        "item_id": item.id,
        "name": item.name,
        "category": item.category,
        "geometry": {
            "roc_mm": "flat" if item.roc_is_flat else item.roc_mm,
            "diameter_mm": item.diameter_mm,
            "dimensions": item.dimensions,
        },
        "quantity": item.quantity,
        "location": item.location,
        "raw_spec": (item.raw_spec or "")[:160],
        "hard_violations": hard,
        "parameters": params,
        "unknowns": unknowns,
        "must_measure": must_measure,
        "eligible": not hard,
        "parse_confidence": item.parse_confidence,
    }


def _dominates(a: dict, b: dict) -> bool:
    """A dominates B: no worse on every comparable dimension, better on one.

    The dimensions must cover every axis a user would trade off, otherwise a
    candidate that is better on an unmodelled axis can be wrongly dominated.
    Spec compliance (stated vs unknown reflectivity) and aperture margin are
    therefore first-class dimensions alongside coating status, unknown count and
    curvature deviation.  All dimensions are "lower is better".
    """
    order = {"design_match": 0, "maybe_usable": 1, "unknown": 2}

    def coat_rank(v):
        ranks = [order.get(c["status"], 3) for c in v["parameters"].get("coatings", [])]
        return max(ranks) if ranks else 3

    def threshold_rank(v):
        # 0 = every required threshold is stated and met, 1 = some unstated.
        states = [c.get("threshold_ok") for c in v["parameters"].get("coatings", [])]
        return 0 if states and all(s is True for s in states) else 1

    def unknown_count(v):
        return len(v["unknowns"]) + len(v["must_measure"])

    def roc_dev(v):
        roc = v["parameters"].get("roc") or {}
        return roc.get("deviation_pct", 0.0) or 0.0

    def aperture_deficit(v):
        # smaller is better: 0 when the aperture margin is unknown or generous
        dia = v["parameters"].get("diameter") or {}
        margin = dia.get("margin_mm")
        return 0.0 if margin is None else max(0.0, -float(margin))

    dims_a = (coat_rank(a), threshold_rank(a), unknown_count(a), roc_dev(a), aperture_deficit(a))
    dims_b = (coat_rank(b), threshold_rank(b), unknown_count(b), roc_dev(b), aperture_deficit(b))
    return all(x <= y for x, y in zip(dims_a, dims_b)) and dims_a != dims_b


def evaluate_candidates(db: Session, requirement: dict) -> dict:
    """Evaluate the whole inventory against one requirement spec.

    Returns eligible verdicts (frontier flagged, frontier first), a rejection
    census, and the requirement echo.  Deterministic; safe to audit.
    """
    query = db.query(InventoryItem).options(selectinload(InventoryItem.coatings))
    category = requirement.get("category")
    if category:
        query = query.filter(InventoryItem.category == category)
    items = query.all()

    # One grouped query rather than a loan lookup per item.
    open_loans = dict(
        db.query(InventoryLoan.item_id, func.coalesce(func.sum(InventoryLoan.quantity), 0.0))
        .filter(InventoryLoan.returned_at.is_(None))
        .group_by(InventoryLoan.item_id)
        .all()
    )

    verdicts = [evaluate_item(item, requirement, float(open_loans.get(item.id, 0.0)))
                for item in items]
    eligible = [v for v in verdicts if v["eligible"]]
    rejected = [v for v in verdicts if not v["eligible"]]

    for v in eligible:
        v["frontier"] = not any(_dominates(o, v) for o in eligible if o is not v)
    eligible.sort(key=lambda v: (
        not v["frontier"],
        max((["design_match", "maybe_usable", "unknown"].index(c["status"])
             if c["status"] in ("design_match", "maybe_usable", "unknown") else 3
             for c in v["parameters"].get("coatings", [])), default=3),
        len(v["unknowns"]) + len(v["must_measure"]),
    ))

    rejection_reasons: dict[str, int] = {}
    for v in rejected:
        for reason in v["hard_violations"]:
            key = reason.split("(")[0][:30]
            rejection_reasons[key] = rejection_reasons.get(key, 0) + 1

    return {
        "status": "completed",
        "tool": "component_match",
        "requirement": requirement,
        "total_evaluated": len(verdicts),
        "eligible_count": len(eligible),
        "rejected_count": len(rejected),
        "rejection_reasons": rejection_reasons,
        "candidates": eligible[: int(requirement.get("max_results", 10))],
        "rejected_examples": rejected[:3],
        "summary": (
            f"{len(verdicts)} 件评估: {len(eligible)} 件可入围"
            f"({sum(1 for v in eligible if v.get('frontier'))} 件在非支配前沿), "
            f"{len(rejected)} 件硬伤淘汰。"
        ),
        "disclaimer": (
            "逐参数确定性判定;'maybe_usable' 基于标称波长的物理阻带先验(非实测曲线), "
            "上台前按 must_measure 清单实测。"
        ),
    }
