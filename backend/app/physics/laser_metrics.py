"""Laser characterization metrics from measured data.

Deterministic analysis of the lab's core measurement — output power vs pump
power — plus the classical multi-curve loss analyses:

- :func:`fit_power_curve`  — threshold pump power + slope efficiency from one
  measured (P_pump, P_out) series, with automatic linear-region detection.
- :func:`findlay_clay`     — round-trip passive loss L from thresholds measured
  with different output-coupler transmissions (P_th linear in T + L).
- :func:`caird`            — intrinsic slope efficiency and loss from slopes
  measured with different output couplings (1/eta linear in 1/T).

Pure numpy; all fits are ordinary least squares with explicit quality metrics.
Reference: Koechner, *Solid-State Laser Engineering*; Findlay & Clay,
Phys. Lett. 20, 277 (1966); Caird et al., IEEE JQE 24, 1077 (1988).
"""
from __future__ import annotations

import numpy as np


def _as_float(value) -> float | None:
    """Coerce a user/JSON-supplied value to float, or None if it is not numeric."""
    if value is None or isinstance(value, bool):
        return None
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    return result if np.isfinite(result) else None


def _as_fraction(value) -> float | None:
    """Coerce an output-coupler transmission in percent to a 0-1 fraction."""
    pct = _as_float(value)
    if pct is None or not (0.0 <= pct <= 100.0):
        return None
    return pct / 100.0


def _linear_fit(x: np.ndarray, y: np.ndarray) -> tuple[float, float, float]:
    """OLS y = a*x + b.  Returns (a, b, r_squared)."""
    a, b = np.polyfit(x, y, 1)
    pred = a * x + b
    ss_res = float(np.sum((y - pred) ** 2))
    ss_tot = float(np.sum((y - np.mean(y)) ** 2))
    r2 = 1.0 - ss_res / ss_tot if ss_tot > 0 else 0.0
    return float(a), float(b), r2


def fit_power_curve(pump: list[float], output: list[float]) -> dict:
    """Fit threshold and slope efficiency from a measured power curve.

    The series has a below-threshold region (output ~ 0) and an above-threshold
    linear region.  The split is chosen by a **piecewise (hockey-stick) fit**:
    for every candidate split the total squared error over ALL points is scored
    as ``sum(y^2)`` below the split (the sub-threshold model is y = 0) plus the
    linear-fit residual above it, and the split minimizing that total wins.

    Scoring every point for every candidate is what keeps the choice unbiased.
    Selecting on the upper segment's R^2 alone is not: a shorter segment always
    fits a line more easily, so that rule drifts to a 3-4 point tail and can
    report a confidently wrong threshold (R^2 = 1 on a spurious collinear tail).

    Returns an honest result: fit quality (``r_squared`` of the upper segment,
    ``model_r_squared`` of the whole piecewise model), the number of points
    used, and warnings for a short linear region, poor linearity, a negative
    threshold, or sub-threshold points that are not actually near zero.
    """
    p = np.asarray(pump, dtype=float)
    o = np.asarray(output, dtype=float)
    if p.size != o.size or p.size < 3:
        return {"status": "failed", "message": "需要至少 3 个 (泵浦, 输出) 数据点"}
    order = np.argsort(p)
    p, o = p[order], o[order]

    best = None  # (total_sse, a, b, r2, split)
    for split in range(0, p.size - 2):
        xs, ys = p[split:], o[split:]
        a, b, r2 = _linear_fit(xs, ys)
        if a <= 0:
            continue
        upper_sse = float(np.sum((ys - (a * xs + b)) ** 2))
        lower_sse = float(np.sum(o[:split] ** 2))  # below threshold the model is y = 0
        total_sse = upper_sse + lower_sse
        if best is None or total_sse < best[0]:
            best = (total_sse, a, b, r2, split)
    if best is None:
        return {"status": "failed", "message": "未找到正斜率的线性区(输出未随泵浦增长)"}

    total_sse, a, b, r2, split = best
    threshold = -b / a

    ss_tot = float(np.sum((o - np.mean(o)) ** 2))
    model_r2 = 1.0 - total_sse / ss_tot if ss_tot > 0 else 0.0

    warnings = []
    if p.size - split < 4:
        warnings.append("线性区数据点较少(<4),阈值/斜率不确定度大")
    if r2 < 0.98:
        warnings.append(f"线性拟合 R²={r2:.3f} 偏低,检查数据或热效应翻卷")
    if model_r2 < 0.95:
        warnings.append(f"整体折线模型 R²={model_r2:.3f} 偏低,数据可能不是典型阈值曲线")
    if split > 0:
        below_max = float(np.max(np.abs(o[:split])))
        if below_max > 0.05 * float(np.max(o)):
            warnings.append("阈值以下的点并非接近零,阈值判定可疑")

    # Slope consistency: a real single-slope region has the same slope in its
    # lower and upper halves.  A mismatch means thermal roll-over or a kinked
    # curve, where a single line silently biases the extrapolated threshold.
    upper_n = p.size - split
    if upper_n >= 6:
        mid = split + upper_n // 2
        a_lo, _, _ = _linear_fit(p[split:mid + 1], o[split:mid + 1])
        a_hi, _, _ = _linear_fit(p[mid:], o[mid:])
        if a_lo > 0 and a_hi > 0:
            ratio = max(a_lo, a_hi) / min(a_lo, a_hi)
            if ratio > 1.15:
                warnings.append(
                    f"高低泵浦段斜率不一致({a_lo * 100:.1f}% vs {a_hi * 100:.1f}%),"
                    "曲线可能存在热翻卷或双斜率,单直线外推的阈值仅供参考"
                )
    if threshold < 0:
        warnings.append("拟合阈值为负 — 数据可能全部远高于阈值,阈值外推不可靠")

    return {
        "status": "completed",
        "threshold_pump": round(float(threshold), 4),
        "slope_efficiency": round(float(a), 4),
        "slope_efficiency_pct": round(float(a) * 100.0, 2),
        "r_squared": round(r2, 5),
        "model_r_squared": round(model_r2, 5),
        "points_total": int(p.size),
        "points_in_fit": int(p.size - split),
        "fit_line": {"a": round(a, 6), "b": round(float(b), 6)},
        "max_output": round(float(o.max()), 4),
        "at_max_pump": round(float(p.max()), 4),
        "warnings": warnings,
    }


def findlay_clay(series: list[dict]) -> dict | None:
    """Findlay-Clay round-trip loss from thresholds at different output couplings.

    Each entry: ``{"output_coupler_T_pct": T, "threshold_pump": P_th}``.
    Model: P_th = K * (T + L) with T, L as fractional round-trip quantities
    (small-loss approximation, -ln(R) ~ T).  Needs >= 2 distinct T values.
    Returns the loss estimate L (in %) or None when not applicable.
    """
    pts = []
    for s in series:
        t = _as_fraction(s.get("output_coupler_T_pct"))
        pth = _as_float(s.get("threshold_pump"))
        if t is not None and pth is not None:
            pts.append((t, pth))
    if len({t for t, _ in pts}) < 2:
        return None
    t = np.array([x for x, _ in pts])
    pth = np.array([y for _, y in pts])
    a, b, r2 = _linear_fit(t, pth)
    if a <= 0:
        return {"applicable": False, "note": "阈值未随 T 增大,Findlay-Clay 假设不成立"}
    loss = b / a  # P_th = a*(T+L) => intercept b = a*L
    result = {
        "applicable": True,
        "round_trip_loss_pct": round(float(loss) * 100.0, 3),
        "r_squared": round(r2, 4),
        "n_points": len(pts),
        "assumptions": "小损耗近似 (-ln R ≈ T);各曲线除输出镜外腔况一致",
    }
    if len(pts) < 3:
        result["warning"] = "仅 2 组输出镜数据:直线必然完美穿过两点,R²=1 不代表模型成立,建议再测一组"
    return result


def caird(series: list[dict]) -> dict | None:
    """Caird analysis: intrinsic slope and loss from slopes vs output coupling.

    Each entry: ``{"output_coupler_T_pct": T, "slope_efficiency": eta}``.
    Model: 1/eta = (1/eta0) * (1 + L/T).  Needs >= 2 distinct T values.
    """
    pts = []
    for s in series:
        t = _as_fraction(s.get("output_coupler_T_pct"))
        eta = _as_float(s.get("slope_efficiency"))
        # T = 0 (no output coupling) would divide by zero in the 1/T model.
        if t is not None and t > 0.0 and eta is not None and eta > 0.0:
            pts.append((t, eta))
    if len({t for t, _ in pts}) < 2:
        return None
    inv_t = np.array([1.0 / t for t, _ in pts])
    inv_eta = np.array([1.0 / e for _, e in pts])
    b1, b0, r2 = _linear_fit(inv_t, inv_eta)   # 1/eta = b0 + b1*(1/T)
    if b0 <= 0:
        return {"applicable": False, "note": "拟合截距非正,Caird 模型不适用于该数据"}
    result = {
        "applicable": True,
        "intrinsic_slope_pct": round(100.0 / float(b0), 2),
        "round_trip_loss_pct": round(float(b1 / b0) * 100.0, 3),
        "r_squared": round(r2, 4),
        "n_points": len(pts),
        "assumptions": "1/η = (1/η0)(1 + L/T);各曲线泵浦/模式匹配一致",
    }
    if len(pts) < 3:
        result["warning"] = "仅 2 组输出镜数据:直线必然完美穿过两点,R²=1 不代表模型成立,建议再测一组"
    return result
