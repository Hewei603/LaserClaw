"""Turn a case's parameters into COMPUTED physics facts for the LLM layer.

This is the bridge that keeps the v2 promise: when the Agent writes an
experiment plan, the geometry and angles in it must come from the deterministic
kernel, not from the language model.  :func:`compute_case_physics` inspects the
case parameters, runs whichever deterministic tools apply, and returns a compact
block of authoritative results that is injected into the generation prompt.

Nothing here calls an LLM, and a missing/invalid parameter simply means the
corresponding tool is skipped — never a guess.
"""
from __future__ import annotations

from typing import Any

from .design import design_linear_cavity
from .toolkit import _placement, run_cavity_design, run_coating_tmm, run_phase_match

# Parameter aliases accepted from a case, mapped to the toolkit's names.
_CAVITY_KEYS = ("R1_mm", "R2_mm", "L_mm", "L_scan_mm", "target_waist_mm", "crystal", "wavelength_nm")


def _num(value: Any) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _roc_ok(value: Any) -> bool:
    """True when a mirror entry is usable: a number or an explicit flat marker."""
    if isinstance(value, str):
        return value.strip().lower() in ("flat", "inf", "infinite", "plane", "平镜")
    return _num(value) is not None and _num(value) != 0


def _cavity_config(params: dict) -> dict | None:
    """Build a cavity_design config if the case carries enough USABLE geometry.

    A placeholder such as ``R1_mm: "TBD"`` means the user has not chosen mirrors
    yet, so it must fall through to the design search rather than fail analysis
    and suppress the search.
    """
    r1, r2 = params.get("R1_mm"), params.get("R2_mm")
    if r1 is None and r2 is None:
        return None
    if not all(_roc_ok(v) for v in (r1, r2) if v is not None):
        return None
    cfg: dict[str, Any] = {k: params[k] for k in _CAVITY_KEYS if k in params}
    cfg.setdefault("wavelength_nm", params.get("wavelength_nm", 1064.0))
    # Nothing to solve for without either a fixed length or a scan range.
    if cfg.get("L_mm") is None and not cfg.get("L_scan_mm"):
        cfg["L_scan_mm"] = {"start": 30.0, "stop": 800.0, "step": 5.0}
    return cfg


def _phase_match_configs(params: dict) -> list[dict]:
    """Build phase-match configs for any nonlinear stage described in the case."""
    configs: list[dict] = []
    crystal = params.get("nonlinear_crystal") or params.get("shg_crystal")
    fundamental = _num(params.get("wavelength_nm"))
    if crystal and fundamental:
        configs.append({"crystal": str(crystal).lower(), "lambda1_nm": fundamental,
                        "pm_type": params.get("shg_pm_type", "I"), "_stage": "SHG"})
        if params.get("thg") or params.get("sfg"):
            configs.append({"crystal": str(params.get("thg_crystal") or crystal).lower(),
                            "lambda1_nm": fundamental, "lambda2_nm": fundamental / 2.0,
                            "pm_type": params.get("thg_pm_type", "II"), "_stage": "SFG"})
    return configs


def _coating_configs(params: dict) -> list[dict]:
    """Build coating checks for nominal mirror labels carried by the case."""
    configs = []
    nominal = params.get("mirror_nominal_hr_nm")
    used_at = _num(params.get("wavelength_nm"))
    if _num(nominal) and used_at:
        configs.append({
            "nominal": {"function": "HR", "design_wavelength_nm": _num(nominal)},
            "query_wavelengths_nm": [used_at],
            "aoi_deg": _num(params.get("mirror_aoi_deg")) or 0.0,
        })
    return configs


def _placement_from(candidate: dict) -> list:
    """Element positions (mm from M1) for a searched candidate geometry."""
    return _placement(candidate["length_mm"], candidate.get("crystal"))


def compute_case_physics(
    parameters: dict | None,
    *,
    available_rocs: list | None = None,
) -> dict[str, Any]:
    """Run every deterministic tool the case parameters support.

    ``available_rocs`` lets the caller pass the mirror radii the lab actually
    owns (from the structured inventory) so a searched design is buildable.

    Returns ``{"available": bool, "results": {...}, "tools_run": [...],
    "note": str}``.  ``available`` is False when the case carries no computable
    parameters, in which case the caller should tell the model that no computed
    geometry exists rather than let it invent one.
    """
    params = dict(parameters or {})
    results: dict[str, Any] = {}
    tools: list[str] = []
    skipped: list[str] = []

    def _safe(tool_name: str, fn, cfg):
        """Run a kernel tool; a malformed parameter skips it, never raises.

        ``case.parameters`` is free-form user JSON, so any value can be the
        wrong type. A bad value must not break plan generation — it must simply
        mean 'not computed'.
        """
        try:
            return fn(cfg)
        except Exception as exc:  # noqa: BLE001 - defensive boundary
            skipped.append(f"{tool_name}: {type(exc).__name__}")
            return {"status": "failed"}

    # Search only when the case gives at least one physical hint. With truly
    # empty parameters we must not invent an operating wavelength.
    # A geometry is wavelength-dependent (w ~ sqrt(lambda)), so never design
    # without knowing the operating wavelength — designing at a silent 1064 nm
    # default would hand a Ti:Sa or 532 nm user a confidently wrong cavity.
    lasing_nm = _num(params.get("wavelength_nm"))
    has_hint = lasing_nm is not None and any(
        params.get(k) is not None
        for k in ("wavelength_nm", "crystal", "target_waist_mm", "nonlinear_crystal",
                  "shg_crystal", "gain_medium")
    )

    cavity_cfg = _cavity_config(params)
    if cavity_cfg is None and has_hint:
        # The user gave no mirrors at all — the usual real case. Don't give up
        # and don't let the model guess: SEARCH for a workable geometry, using
        # radii the lab actually owns when we know them.
        wl = lasing_nm
        search = _safe("cavity_search", lambda cfg: design_linear_cavity(**cfg), {
            "wavelength_nm": wl,
            "crystal": params.get("crystal") if isinstance(params.get("crystal"), dict) else None,
            "target_waist_mm": _num(params.get("target_waist_mm")),
            "candidate_rocs": available_rocs,
        })
        if search.get("status") == "completed" and search.get("candidates"):
            best = search["candidates"][0]
            results["cavity_design_search"] = {
                "note": "案例未给定腔镜,以下几何由 LaserClaw 搜索得出(非用户输入)",
                "wavelength_nm": wl,
                "recommended": {
                    "R1": best["R1_label"], "R2": best["R2_label"],
                    "length_mm": best["length_mm"],
                    "waist_w0_mm": best["waist_w0_mm"],
                    "spot_on_mirror1_mm": best.get("w_on_mirror1_mm"),
                    "spot_on_mirror2_mm": best.get("w_on_mirror2_mm"),
                    "spot_in_crystal_mm": best.get("w_in_crystal_mm"),
                    "stability_m": best["stability_m"],
                    "thermal_lens_tolerance_dioptre": best.get("thermal_lens_tolerance_dioptre"),
                    "thermal_lens_tolerance_min_f_mm": best.get("thermal_lens_tolerance_min_f_mm"),
                    "score_breakdown": best.get("score_breakdown"),
                    "element_placement": _placement_from(best),
                },
                "alternatives": [
                    {"R1": c["R1_label"], "R2": c["R2_label"], "length_mm": c["length_mm"],
                     "waist_w0_mm": c["waist_w0_mm"], "score": c["score"]}
                    for c in search["candidates"][1:]
                ],
                "search_space": search["search_space"],
                "objective": search["objective"],
                "caveats": search["caveats"],
            }
            tools.append("cavity_design_search")
    if cavity_cfg:
        out = _safe("cavity_design", run_cavity_design, cavity_cfg)
        if out.get("status") == "completed":
            rec = out.get("recommended") or out.get("analysis") or {}
            results["cavity_design"] = {
                "summary": out.get("summary"),
                "stable_windows_mm": (out.get("scan") or {}).get("stable_windows_mm"),
                "recommended_length_mm": rec.get("length_mm"),
                "waist_w0_mm": rec.get("waist_w0_mm"),
                "spot_on_mirror1_mm": rec.get("w_on_mirror1_mm"),
                "spot_on_mirror2_mm": rec.get("w_on_mirror2_mm"),
                "spot_in_crystal_mm": rec.get("w_in_crystal_mm"),
                "stability_m": rec.get("stability_m"),
                "element_placement": out.get("placement"),
            }
            tools.append("cavity_design")

    for cfg in _phase_match_configs(params):
        stage = cfg.pop("_stage")
        out = _safe(f"phase_match:{stage}", run_phase_match, cfg)
        if out.get("status") == "completed":
            matched = [s for s in out.get("solutions", []) if s.get("theta_deg") is not None]
            if matched:
                results.setdefault("phase_matching", {})[stage] = {
                    "crystal": cfg["crystal"],
                    "type": cfg.get("pm_type"),
                    "solutions": matched[:3],
                    "note": out.get("disclaimer"),
                }
                tools.append(f"phase_match:{stage}")

    for cfg in _coating_configs(params):
        out = _safe("coating_tmm", run_coating_tmm, cfg)
        if out.get("status") == "completed":
            results["coating_check"] = {
                "summary": out.get("summary"),
                "query_results": out.get("query_results"),
                "confidence": out.get("confidence"),
                "recommend_measurement": out.get("recommend_measurement"),
            }
            tools.append("coating_tmm")

    return {
        "available": bool(results),
        "tools_run": tools,
        "skipped": skipped,
        "results": results,
        "note": (
            "These values were computed by LaserClaw's deterministic physics kernel "
            "(ABCD/Gaussian, Sellmeier phase matching, thin-film TMM) for "
            f"{lasing_nm if lasing_nm else 'the stated'} nm. Use them as-is in the "
            "generated content, state the wavelength they belong to, and do not "
            "recompute or round them differently."
            if results else
            "No computable cavity/nonlinear parameters were supplied, so no geometry "
            "was computed. Do not invent lengths, angles or spot sizes; state that they "
            "must be computed with the cavity_design module once mirrors are chosen."
        ),
    }
