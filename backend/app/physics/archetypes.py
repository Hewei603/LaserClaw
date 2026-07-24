"""Standard coating archetypes and stopband estimates.

The inverse problem "given only a nominal label (e.g. '1123 nm HR'), what is the
real part's reflectance curve" is UNSOLVABLE: infinitely many real layer stacks
satisfy one datasheet label.  What physics *can* give is a *representative*
archetype and, crucially, the stopband **width** of a quarter-wave high
reflector, which depends only on the index contrast (the number of pairs sets
depth/edge steepness, not width).

So this module produces:

- :func:`build_hr_qwot`     — a standard (HL)^N quarter-wave high reflector
- :func:`build_ar_singlelayer` — a standard single-layer quarter-wave AR
- :func:`stopband_edges`    — closed-form HR high-reflectance band edges
- :func:`archetype_stopband_estimate` — the honest Mode-B answer: an interval,
  a width *bracket* across plausible material contrasts, an AOI blue-shift, and
  the categorical position of a query wavelength — never a fake scalar margin.

Reference: Macleod, *Thin-Film Optical Filters* (quarter-wave stack stopband).
"""
from __future__ import annotations

import math

import numpy as np

from .materials import n_real
from .tmm import Layer, Stack, spectrum

# Representative deposited-film index pairs for the contrast bracket.  These
# bracket the plausible stopband width of a real HR whose true design is unknown.
_LOW_CONTRAST_PAIR = ("ta2o5_film", "al2o3_film")   # narrow stopband
_HIGH_CONTRAST_PAIR = ("tio2_film", "sio2_film")    # wide stopband
_DEFAULT_PAIR = ("ta2o5_film", "sio2_film")         # typical IBS HR


def stopband_edges(lambda0_nm: float, n_high: float, n_low: float) -> tuple[float, float, float]:
    """High-reflectance band edges of a quarter-wave (HL)^N stack.

    Returns ``(lambda_short_nm, lambda_long_nm, fractional_width)``.

    The band is symmetric in normalized frequency ``g = lambda0/lambda`` with
    half-width ``dg = (2/pi) arcsin(rho)``, ``rho = (nH-nL)/(nH+nL)`` — so it is
    asymmetric in wavelength (physically correct).
    """
    rho = (n_high - n_low) / (n_high + n_low)
    dg = (2.0 / math.pi) * math.asin(rho)
    lambda_short = lambda0_nm / (1.0 + dg)
    lambda_long = lambda0_nm / (1.0 - dg)
    frac_width = (lambda_long - lambda_short) / lambda0_nm
    return lambda_short, lambda_long, frac_width


def build_hr_qwot(
    lambda0_nm: float,
    target_R: float = 0.995,
    n_pairs: int | None = None,
    high: str = "ta2o5_film",
    low: str = "sio2_film",
    substrate: str = "fused_silica",
    incident: str = "air",
) -> Stack:
    """Build a standard (HL)^N quarter-wave high reflector centred at *lambda0_nm*.

    If *n_pairs* is None it is solved to reach *target_R* at normal incidence,
    using the closed-form equivalent admittance ``Y = (nH/nL)^{2N} * ns``.
    Layers are ordered incident-side first (H first, L adjacent to substrate).
    """
    nH = n_real(high, lambda0_nm)
    nL = n_real(low, lambda0_nm)
    ns = n_real(substrate, lambda0_nm)
    n0 = n_real(incident, lambda0_nm)

    if n_pairs is None:
        # A perfect reflector needs infinite pairs; cap target_R just below 1.
        target_R = min(float(target_R), 0.99999)
        sqrtR = math.sqrt(target_R)
        # Y solved from R = ((n0 - Y)/(n0 + Y))^2 for a high reflector (Y >> n0).
        y_target = n0 * (1.0 + sqrtR) / (1.0 - sqrtR)
        n_pairs = max(1, math.ceil(math.log(y_target / ns) / (2.0 * math.log(nH / nL))))

    dH = lambda0_nm / (4.0 * nH)
    dL = lambda0_nm / (4.0 * nL)
    layers: list[Layer] = []
    for _ in range(int(n_pairs)):
        layers.append(Layer(thickness_nm=dH, material=high))
        layers.append(Layer(thickness_nm=dL, material=low))
    return Stack(layers=layers, incident=incident, substrate=substrate)


def build_ar_singlelayer(
    lambda0_nm: float,
    substrate: str = "fused_silica",
    material: str | None = "mgf2_film",
    incident: str = "air",
) -> Stack:
    """Build a standard single-layer quarter-wave AR centred at *lambda0_nm*.

    With ``material=None`` an *ideal* layer of index ``sqrt(n0*ns)`` is used
    (perfect AR at design).  Otherwise a real film (default MgF2) is used, which
    is only a partial AR unless its index happens to equal ``sqrt(n0*ns)``.
    """
    ns = n_real(substrate, lambda0_nm)
    n0 = n_real(incident, lambda0_nm)
    if material is None:
        n_ar = math.sqrt(n0 * ns)
        d = lambda0_nm / (4.0 * n_ar)
        return Stack(layers=[Layer(thickness_nm=d, n=n_ar)], incident=incident, substrate=substrate)
    n_ar = n_real(material, lambda0_nm)
    d = lambda0_nm / (4.0 * n_ar)
    return Stack(layers=[Layer(thickness_nm=d, material=material)], incident=incident, substrate=substrate)


def _measured_band_edges(stack: Stack, aoi_deg: float, pol: str, lambda0_nm: float) -> tuple[float, float, float]:
    """Contiguous high-reflectance band of an actual stack, measured by TMM.

    Returns ``(short_nm, long_nm, center_nm)`` of the contiguous region around the
    reflectance peak where ``R >= 0.5 * R_peak`` (the conventional stopband edge
    for a finite quarter-wave stack).  Used for the honest s/p split at oblique
    incidence, where no simple closed form applies.
    """
    lo = lambda0_nm * 0.5
    hi = lambda0_nm * 1.6
    grid = np.linspace(lo, hi, 1400)
    R = spectrum(stack, grid, aoi_deg=aoi_deg, pol=pol)["R"]
    peak_i = int(np.argmax(R))
    thresh = 0.5 * R[peak_i]
    lo_i = peak_i
    while lo_i > 0 and R[lo_i - 1] >= thresh:
        lo_i -= 1
    hi_i = peak_i
    while hi_i < len(grid) - 1 and R[hi_i + 1] >= thresh:
        hi_i += 1
    return float(grid[lo_i]), float(grid[hi_i]), float(grid[peak_i])


def _aoi_center_shift(lambda0_nm: float, stack: Stack, aoi_deg: float, pol: str,
                      n_high: float, n_low: float) -> dict:
    """Exact archetype center-wavelength blue-shift with AOI, plus closed-form check."""
    if aoi_deg == 0.0:
        return {"center_shift_nm": 0.0, "closed_form_center_nm": lambda0_nm, "center_nm": lambda0_nm}
    # Exact: argmax R over a grid around the (blue-shifted) center.
    lo = lambda0_nm * 0.6
    hi = lambda0_nm * 1.05
    grid = np.linspace(lo, hi, 900)
    R = spectrum(stack, grid, aoi_deg=aoi_deg, pol=pol)["R"]
    center = float(grid[int(np.argmax(R))])
    # Closed-form quick check using the actual stack's materials:
    # lambda_c(theta) ~ lambda0 * sqrt(1 - (sin/n_eff)^2).
    n_eff = math.sqrt(n_high * n_low)
    theta = math.radians(aoi_deg)
    cf = lambda0_nm * math.sqrt(1.0 - (math.sin(theta) / n_eff) ** 2)
    return {"center_shift_nm": center - lambda0_nm, "closed_form_center_nm": cf, "center_nm": center}


def _band_position(query_nm: float, short_nm: float, long_nm: float, edge_frac: float = 0.06) -> tuple[str, float]:
    """Categorical position of a query wavelength relative to the HR stopband.

    Returns ``(position, margin_to_nearest_edge_nm)`` where position is one of
    ``inside`` / ``edge`` / ``outside``.  ``edge`` is a transition zone of
    ``edge_frac`` of the band width around each edge.
    """
    width = long_nm - short_nm
    edge = edge_frac * width
    if short_nm + edge <= query_nm <= long_nm - edge:
        pos = "inside"
    elif short_nm - edge <= query_nm <= long_nm + edge:
        pos = "edge"
    else:
        pos = "outside"
    margin = min(abs(query_nm - short_nm), abs(query_nm - long_nm))
    if query_nm < short_nm or query_nm > long_nm:
        margin = -margin  # negative = outside the band
    return pos, margin


def archetype_stopband_estimate(
    lambda0_nm: float,
    function: str = "HR",
    query_wavelengths_nm: list[float] | None = None,
    aoi_deg: float = 0.0,
    pol: str = "avg",
    high: str = "ta2o5_film",
    low: str = "sio2_film",
    substrate: str = "fused_silica",
    target_R: float = 0.995,
    contrast_bracket: bool = True,
) -> dict:
    """Honest Mode-B estimate for a nominal-label coating.

    Produces the stopband interval, a width *bracket* across low/high contrast
    material pairs, an AOI blue-shift, and the categorical ``band_position`` of
    each query wavelength.  Everything is marked ``is_representative_only`` /
    ``confidence='low'`` and ``recommend_measurement=True``: this is a physics
    prior, not the real part's curve.

    Only ``HR`` uses the stopband model.  ``AR`` returns a coarse "designed at
    lambda0, degrades away from it" note (a real AR has no stopband).
    """
    function = function.upper()
    nH = n_real(high, lambda0_nm)
    nL = n_real(low, lambda0_nm)

    if function != "HR":
        # AR: no stopband; reflectivity is minimal at design and rises away from it.
        result = {
            "function": function,
            "design_wavelength_nm": lambda0_nm,
            "model": "single_layer_AR_archetype",
            "confidence": "low",
            "is_representative_only": True,
            "recommend_measurement": True,
            "query_results": [],
            "assumptions": ["ideal single-layer QW AR", "no substrate backside"],
            "disclaimer": (
                "AR archetype: reflectivity is minimal at the design wavelength and rises "
                "away from it; a real multilayer AR band is broader. NOT the real part's curve."
            ),
        }
        for q in (query_wavelengths_nm or []):
            frac_detune = abs(q - lambda0_nm) / lambda0_nm
            pos = "low_R" if frac_detune < 0.05 else ("edge" if frac_detune < 0.15 else "high_R")
            result["query_results"].append(
                {"wavelength_nm": q, "band_position": pos, "detune_frac": frac_detune, "is_representative_only": True}
            )
        return result

    # 'high'/'low' are named roles; if the caller mislabels them, use the
    # physical high/low so the stopband is never returned inverted.
    if nH < nL:
        nH, nL = nL, nH
        high, low = low, high

    short_nm, long_nm, frac = stopband_edges(lambda0_nm, nH, nL)
    center_nm = 0.5 * (short_nm + long_nm)
    width_nm = long_nm - short_nm

    # Width bracket across plausible real contrasts.
    width_bracket = None
    if contrast_bracket:
        widths = []
        for hi_mat, lo_mat in (_LOW_CONTRAST_PAIR, _HIGH_CONTRAST_PAIR):
            s2, l2, _ = stopband_edges(lambda0_nm, n_real(hi_mat, lambda0_nm), n_real(lo_mat, lambda0_nm))
            widths.append(l2 - s2)
        width_bracket = [round(min(widths), 2), round(max(widths), 2)]

    # AOI blue-shift from the archetype stack.
    stack = build_hr_qwot(lambda0_nm, target_R=target_R, high=high, low=low, substrate=substrate)
    aoi = _aoi_center_shift(lambda0_nm, stack, aoi_deg, pol, nH, nL)

    # For AOI>0 the s and p stopbands split and blue-shift; measure the REAL s and
    # p high-reflectance bands from the archetype TMM (no simple closed form) and
    # use their intersection (the conservative both-pol band) for band_position.
    edges_s = edges_p = None
    if aoi_deg > 0.0:
        s_s, s_l, _ = _measured_band_edges(stack, aoi_deg, "s", lambda0_nm)
        p_s, p_l, _ = _measured_band_edges(stack, aoi_deg, "p", lambda0_nm)
        edges_s = [round(s_s, 2), round(s_l, 2)]
        edges_p = [round(p_s, 2), round(p_l, 2)]
        # both-pol usable band = intersection of the s and p bands
        short_nm, long_nm = max(s_s, p_s), min(s_l, p_l)
        center_nm = 0.5 * (short_nm + long_nm)

    query_results = []
    for q in (query_wavelengths_nm or []):
        pos, margin = _band_position(q, short_nm, long_nm)
        query_results.append(
            {
                "wavelength_nm": q,
                "band_position": pos,
                "margin_to_edge_nm": round(margin, 2),
                "is_representative_only": True,
            }
        )

    return {
        "function": "HR",
        "design_wavelength_nm": lambda0_nm,
        "model": "HL_qwot_archetype",
        "confidence": "low",
        "is_representative_only": True,
        "recommend_measurement": True,
        "stopband": {
            "center_nm": round(center_nm, 2),
            "edges_nm": [round(short_nm, 2), round(long_nm, 2)],
            "width_nm": round(width_nm, 2),
            "fractional_width": round(frac, 4),
            "edges_s_nm": edges_s,
            "edges_p_nm": edges_p,
            "width_bracket_nm": width_bracket,
        },
        "aoi": {
            "aoi_deg": aoi_deg,
            "center_shift_nm": round(aoi["center_shift_nm"], 2),
            "closed_form_center_nm": round(aoi["closed_form_center_nm"], 2),
        },
        "archetype": {
            "high": high,
            "n_high": round(nH, 4),
            "low": low,
            "n_low": round(nL, 4),
            "n_pairs": len(stack.layers) // 2,
            "substrate": substrate,
            "target_R": target_R,
        },
        "query_results": query_results,
        "assumptions": [
            "ideal QWOT layers",
            "no thickness error",
            "semi-infinite substrate",
            "representative deposited-film indices",
        ],
        "disclaimer": (
            f"Archetype (HL)^{len(stack.layers)//2} {high}/{low}; NOT the real part's curve. "
            "Stopband width is a physics prior from index contrast. Bench measurement recommended."
        ),
    }
