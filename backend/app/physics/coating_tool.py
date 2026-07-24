"""Dual-mode coating evaluation — the single entrypoint for all coating questions.

``evaluate_coating(request)`` answers "what does this coating do at these
wavelengths" honestly, choosing one of three modes:

- **exact_stack**  : a known layer stack -> forward TMM, ``confidence='high'``.
- **vendor_curve** : a digitized/measured (lambda, R/T) curve -> interpolation,
  ``confidence='high'`` (it *is* the spec'd curve).
- **archetype**    : only a nominal label ``{function, design_wavelength_nm}`` ->
  a representative stopband estimate, ``confidence='low'`` +
  ``recommend_measurement=True``.  The inverse problem is unsolvable; we return
  an interval and categorical band position, never a fake point value that L1
  could mistake for the real curve.

The result dict matches the case-module compute convention (``status`` in
``needs_input`` | ``failed`` | ``completed``) so the API adapter is a thin
unpacker.  This module imports only numpy + the physics package — no web/DB/LLM.
"""
from __future__ import annotations

import math

import numpy as np

from .archetypes import archetype_stopband_estimate
from .tmm import Layer, Stack, solve_stack


def _interp_curve(curve: dict, wavelengths: list[float], key: str) -> list[float | None]:
    xs = np.asarray(curve.get("wl_nm", []), dtype=float)
    ys = curve.get(key)
    if ys is None or len(xs) == 0:
        return [None] * len(wavelengths)
    ys = np.asarray(ys, dtype=float)
    order = np.argsort(xs)
    xs, ys = xs[order], ys[order]
    out: list[float | None] = []
    for w in wavelengths:
        if w < xs[0] or w > xs[-1]:
            out.append(None)  # outside measured range: honest null, no extrapolation
        else:
            val = float(np.interp(w, xs, ys))
            out.append(None if math.isnan(val) else val)  # NaN in the source curve -> honest null
    return out


def _eval_exact_stack(request: dict) -> dict:
    stack_spec = request["stack"]
    layers = []
    for ly in stack_spec.get("layers", []):
        layers.append(
            Layer(
                thickness_nm=float(ly["thickness_nm"]),
                material=ly.get("material"),
                n=(complex(ly["n"]) if ly.get("n") is not None else None),
            )
        )
    stack = Stack(
        layers=layers,
        incident=stack_spec.get("incident", "air"),
        substrate=stack_spec.get("substrate", "fused_silica"),
    )
    aoi = float(request.get("aoi_deg", 0.0))
    pol = request.get("polarization", "avg")
    query = [float(w) for w in request["query_wavelengths_nm"]]
    query_results = []
    for w in query:
        res = solve_stack(stack, w, aoi_deg=aoi, pol=pol)
        query_results.append(
            {
                "wavelength_nm": w,
                "R": round(res["R"], 6),
                "T": round(res["T"], 6),
                "A": round(res["A"], 6),
                "is_representative_only": False,
            }
        )
    return {
        "status": "completed",
        "mode_used": "exact_stack",
        "confidence": "high",
        "polarization": pol,
        "aoi_deg": aoi,
        "query_results": query_results,
        "assumptions": [
            "ideal flat parallel isotropic layers",
            "semi-infinite substrate (backside ignored)",
            "no deposition thickness/index error",
        ],
        "recommend_measurement": False,
        "summary": f"Exact TMM on a {len(layers)}-layer stack at {len(query)} wavelength(s).",
    }


def _eval_vendor_curve(request: dict) -> dict:
    curve = request["vendor_curve"]
    query = [float(w) for w in request["query_wavelengths_nm"]]
    r_vals = _interp_curve(curve, query, "R")
    t_vals = _interp_curve(curve, query, "T")
    query_results = []
    for w, r, t in zip(query, r_vals, t_vals):
        query_results.append(
            {
                "wavelength_nm": w,
                "R": None if r is None else round(r, 6),
                "T": None if t is None else round(t, 6),
                "in_measured_range": r is not None or t is not None,
                "is_representative_only": False,
            }
        )
    return {
        "status": "completed",
        "mode_used": "vendor_curve",
        "confidence": "high",
        "query_results": query_results,
        "assumptions": ["values interpolated from the supplied vendor/measured curve"],
        "recommend_measurement": False,
        "source": curve.get("source", ""),
        "summary": f"Interpolated the supplied curve at {len(query)} wavelength(s).",
    }


def _eval_archetype(request: dict) -> dict:
    nominal = request["nominal"]
    query = [float(w) for w in request.get("query_wavelengths_nm", [])]
    est = archetype_stopband_estimate(
        lambda0_nm=float(nominal["design_wavelength_nm"]),
        function=nominal.get("function", "HR"),
        query_wavelengths_nm=query,
        aoi_deg=float(request.get("aoi_deg", 0.0)),
        pol=request.get("polarization", "avg"),
        high=nominal.get("high", "ta2o5_film"),
        low=nominal.get("low", "sio2_film"),
        substrate=nominal.get("substrate", "fused_silica"),
        target_R=float(nominal.get("target_R", 0.995)),
    )
    est["status"] = "completed"
    est["mode_used"] = "archetype"
    sb = est.get("stopband")
    if sb:
        est["summary"] = (
            f"Nominal {nominal.get('function','HR')} at {nominal['design_wavelength_nm']} nm: "
            f"archetype stopband ~{sb['edges_nm'][0]}-{sb['edges_nm'][1]} nm."
        )
    return est


def evaluate_coating(request: dict) -> dict:
    """Evaluate a coating in the mode implied by *request*.

    ``mode`` may be given explicitly (``exact_stack`` | ``vendor_curve`` |
    ``archetype``) or left as ``auto`` (default), which infers from which
    payload is present, preferring exact data.
    """
    mode = request.get("mode", "auto")
    has_stack = bool(request.get("stack"))
    has_curve = bool(request.get("vendor_curve"))
    has_nominal = bool(request.get("nominal"))

    if mode == "auto":
        if has_stack:
            mode = "exact_stack"
        elif has_curve:
            mode = "vendor_curve"
        elif has_nominal:
            mode = "archetype"
        else:
            return {
                "status": "needs_input",
                "message": "Provide a stack, a vendor R/T curve, or a nominal {function, design_wavelength_nm}.",
            }

    if not request.get("query_wavelengths_nm") and mode != "archetype":
        return {"status": "needs_input", "message": "query_wavelengths_nm is required."}

    try:
        if mode == "exact_stack":
            return _eval_exact_stack(request)
        if mode == "vendor_curve":
            return _eval_vendor_curve(request)
        if mode == "archetype":
            return _eval_archetype(request)
    except (KeyError, ValueError, ArithmeticError) as exc:
        return {"status": "failed", "message": f"Coating evaluation failed: {exc}"}
    return {"status": "failed", "message": f"Unknown coating mode '{mode}'."}
