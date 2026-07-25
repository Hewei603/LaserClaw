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
    linear region.  The split point is chosen automatically: for every candidate
    split, fit the upper segment and keep the split maximizing R^2 (minimum 3
    points).  Threshold = x-intercept of the winning line; slope efficiency =
    its slope (same units in/out -> dimensionless, reported as %).

    Returns an honest result: fit quality (r_squared), number of points used,
    and warnings (too few points, poor linearity, negative slope).
    """
    p = np.asarray(pump, dtype=float)
    o = np.asarray(output, dtype=float)
    if p.size != o.size or p.size < 3:
        return {"status": "failed", "message": "需要至少 3 个 (泵浦, 输出) 数据点"}
    order = np.argsort(p)
    p, o = p[order], o[order]

    best = None
    for split in range(0, p.size - 2):
        xs, ys = p[split:], o[split:]
        a, b, r2 = _linear_fit(xs, ys)
        if a <= 0:
            continue
        if best is None or r2 > best[2]:
            best = (a, b, r2, split)
    if best is None:
        return {"status": "failed", "message": "未找到正斜率的线性区(输出未随泵浦增长)"}

    a, b, r2, split = best
    threshold = -b / a
    warnings = []
    if p.size - split < 4:
        warnings.append("线性区数据点较少(<4),阈值/斜率不确定度大")
    if r2 < 0.98:
        warnings.append(f"线性拟合 R²={r2:.3f} 偏低,检查数据或热效应翻卷")
    if threshold < 0:
        warnings.append("拟合阈值为负 — 数据可能全部远高于阈值,阈值外推不可靠")

    return {
        "status": "completed",
        "threshold_pump": round(float(threshold), 4),
        "slope_efficiency": round(float(a), 4),
        "slope_efficiency_pct": round(float(a) * 100.0, 2),
        "r_squared": round(r2, 5),
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
    pts = [(s["output_coupler_T_pct"] / 100.0, s["threshold_pump"]) for s in series
           if s.get("output_coupler_T_pct") is not None and s.get("threshold_pump") is not None]
    if len({t for t, _ in pts}) < 2:
        return None
    t = np.array([x for x, _ in pts])
    pth = np.array([y for _, y in pts])
    a, b, r2 = _linear_fit(t, pth)
    if a <= 0:
        return {"applicable": False, "note": "阈值未随 T 增大,Findlay-Clay 假设不成立"}
    loss = b / a  # P_th = a*(T+L) => intercept b = a*L
    return {
        "applicable": True,
        "round_trip_loss_pct": round(float(loss) * 100.0, 3),
        "r_squared": round(r2, 4),
        "n_points": len(pts),
        "assumptions": "小损耗近似 (-ln R ≈ T);各曲线除输出镜外腔况一致",
    }


def caird(series: list[dict]) -> dict | None:
    """Caird analysis: intrinsic slope and loss from slopes vs output coupling.

    Each entry: ``{"output_coupler_T_pct": T, "slope_efficiency": eta}``.
    Model: 1/eta = (1/eta0) * (1 + L/T).  Needs >= 2 distinct T values.
    """
    pts = [(s["output_coupler_T_pct"] / 100.0, s["slope_efficiency"]) for s in series
           if s.get("output_coupler_T_pct") is not None and (s.get("slope_efficiency") or 0) > 0]
    if len({t for t, _ in pts}) < 2:
        return None
    inv_t = np.array([1.0 / t for t, _ in pts])
    inv_eta = np.array([1.0 / e for _, e in pts])
    b1, b0, r2 = _linear_fit(inv_t, inv_eta)   # 1/eta = b0 + b1*(1/T)
    if b0 <= 0:
        return {"applicable": False, "note": "拟合截距非正,Caird 模型不适用于该数据"}
    return {
        "applicable": True,
        "intrinsic_slope_pct": round(100.0 / float(b0), 2),
        "round_trip_loss_pct": round(float(b1 / b0) * 100.0, 3),
        "r_squared": round(r2, 4),
        "n_points": len(pts),
        "assumptions": "1/η = (1/η0)(1 + L/T);各曲线泵浦/模式匹配一致",
    }
