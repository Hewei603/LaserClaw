"""Coating-string and geometry grammar parser for the lab inventory.

Handles the real-world semi-structured notation observed in the lab workbook:

- surface markers:      ``S1:`` / ``S2:`` / ``S1（凹）:`` / full-width colons
- functions:            ``HR`` ``AR`` ``HT`` and partial transmission ``T=20%``
- thresholds:           ``R>99.5%`` ``T>90%`` ``R<0.2%`` ``T=20%``
- wavelength bands:     ``1064-1066`` (range) vs ``1064`` (single)
- multi-wavelength:     ``880&1053+1314`` ``914/517`` ``808+946+1064``
- at-notation:          ``AR@（970-1080）nm`` ``HR＠1123``
- geometry:             ``R=-100`` ``平镜`` ``D=25.4mm`` ``3*3*25mm3``
                        ``θ=159.6°`` ``c-cut`` ``掺杂浓度5at.%``
- uncertainty markers:  ``未镀膜`` ``切向未知`` ``不能确定`` ``破裂`` ``不明``

Every parse keeps the raw fragment; anything unrecognized lowers
``parse_confidence`` instead of being silently dropped.  Pure stdlib.
"""
from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field

# Normalization: NFKC folds full-width letters/digits/punctuation (Ｒ＞（＠％：)
# to ASCII; the table below covers the few operators NFKC leaves alone.
_EXTRA = str.maketrans({"≥": ">", "≤": "<", "﹥": ">", "﹤": "<"})


def _normalize(text: str) -> str:
    return unicodedata.normalize("NFKC", text).translate(_EXTRA)

UNKNOWN_MARKERS = ("未镀膜", "不镀膜", "切向未知", "不能确定", "未能确定", "不明", "未知")
DAMAGE_MARKERS = ("破裂", "裂纹", "无法维修", "损坏")

# One coating clause: wavelengths + function + optional threshold.
_BAND = r"(\d{3,4}(?:\.\d+)?)(?:\s*-\s*(\d{3,4}(?:\.\d+)?))?"
_FUNC = r"(HR|AR|HT|PR)"
_THRESH = r"([RT])\s*([><=])\s*(\d+(?:\.\d+)?)\s*%?"


@dataclass
class CoatingBand:
    surface: str
    wl_min_nm: float
    wl_max_nm: float
    function: str            # HR | AR | HT | PR
    value_type: str | None = None
    comparator: str | None = None
    value_pct: float | None = None
    raw_fragment: str = ""


@dataclass
class ParsedCoating:
    bands: list[CoatingBand] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)
    confidence: str = "parsed"   # parsed | partial | needs_review


def _wl_ok(v: float) -> bool:
    return 200.0 <= v <= 3200.0


def _split_wavelengths(text: str) -> list[tuple[float, float]]:
    """Expand '880&1053+1314', '914/517', '1064-1066' into (lo, hi) bands."""
    bands: list[tuple[float, float]] = []
    for chunk in re.split(r"[&+/、]", text):
        m = re.fullmatch(r"\s*" + _BAND + r"\s*(?:nm)?\s*", chunk)
        if not m:
            continue
        lo = float(m.group(1))
        hi = float(m.group(2)) if m.group(2) else lo
        if _wl_ok(lo) and _wl_ok(hi) and hi >= lo:
            bands.append((lo, hi))
    return bands


def parse_coating(text: str, surface: str) -> ParsedCoating:
    """Parse one surface's coating cell into typed per-band rows.

    Strategy: split the cell into clauses on commas/semicolons; inside each
    clause, find function tokens and attach the wavelengths that precede or
    follow them (both ``1064HR`` and ``AR@1064`` orders occur), plus an optional
    numeric threshold.  ``T=x%`` with no letter function is a partial reflector.
    """
    out = ParsedCoating()
    if not text or not text.strip():
        return out
    norm = _normalize(text)

    for marker in UNKNOWN_MARKERS:
        if marker in text:
            out.notes.append(marker)
    for marker in DAMAGE_MARKERS:
        if marker in text:
            out.notes.append(marker)
    if any(m in text for m in UNKNOWN_MARKERS):
        out.confidence = "needs_review"
        return out

    # strip a leading surface tag like "S1:" / "S1(凹):"
    norm = re.sub(r"^\s*S[12]\s*(\([^)]*\))?\s*:?", "", norm, flags=re.IGNORECASE)

    clauses = [c for c in re.split(r"[,;]", norm) if c.strip()]
    for clause in clauses:
        clause_raw = clause.strip()
        consumed: list[tuple[int, int]] = []   # character spans already claimed
        found_here = False

        def claim(m: re.Match) -> None:
            consumed.append((m.start(), m.end()))

        def is_free(m: re.Match) -> bool:
            return not any(s < m.end() and m.start() < e for s, e in consumed)

        # Pattern A: FUNC@wavelengths, e.g. AR@(970-1080)nm, HR@1123, AR@880&1053+1314
        for m in re.finditer(_FUNC + r"\s*@\s*\(?\s*([0-9.&+/、\-\s]+?)\s*\)?\s*(?:nm)?(?=[^0-9.&+/、\-]|$)",
                             clause_raw, flags=re.IGNORECASE):
            wls = _split_wavelengths(m.group(2))
            # attach a threshold only if it directly follows this token group
            tail = clause_raw[m.end():m.end() + 20]
            thresh = re.match(r"\s*\(?\s*" + _THRESH, tail)
            for lo, hi in wls:
                out.bands.append(CoatingBand(
                    surface=surface, wl_min_nm=lo, wl_max_nm=hi,
                    function=m.group(1).upper(),
                    value_type=thresh.group(1).upper() if thresh else None,
                    comparator=thresh.group(2) if thresh else None,
                    value_pct=float(thresh.group(3)) if thresh else None,
                    raw_fragment=clause_raw[:250],
                ))
                found_here = True
            if wls:
                claim(m)

        # Pattern B: wavelengths immediately followed by FUNC ("1064-1066HR",
        # "1064HT T>90% 1076HR R>99.5%"), threshold scoped to this token.
        for m in re.finditer(_BAND + r"\s*(?:nm)?\s*" + _FUNC, clause_raw, flags=re.IGNORECASE):
            if not is_free(m):
                continue
            lo = float(m.group(1))
            hi = float(m.group(2)) if m.group(2) else lo
            if not (_wl_ok(lo) and _wl_ok(hi)):
                continue
            tail = clause_raw[m.end():]
            nxt = re.search(_BAND + r"\s*(?:nm)?\s*" + _FUNC, tail, flags=re.IGNORECASE)
            scope = tail[: nxt.start()] if nxt else tail
            thresh = re.search(_THRESH, scope)
            out.bands.append(CoatingBand(
                surface=surface, wl_min_nm=lo, wl_max_nm=hi,
                function=m.group(3).upper(),
                value_type=thresh.group(1).upper() if thresh else None,
                comparator=thresh.group(2) if thresh else None,
                value_pct=float(thresh.group(3)) if thresh else None,
                raw_fragment=clause_raw[:250],
            ))
            claim(m)
            found_here = True

        # Pattern C: bare partial-transmission "1176-1180 T=20%" (no letter function)
        for m in re.finditer(_BAND + r"\s*(?:nm)?\s*" + _THRESH, clause_raw):
            if not is_free(m):
                continue
            lo = float(m.group(1))
            hi = float(m.group(2)) if m.group(2) else lo
            if _wl_ok(lo) and _wl_ok(hi):
                out.bands.append(CoatingBand(
                    surface=surface, wl_min_nm=lo, wl_max_nm=hi,
                    function="PR",
                    value_type=m.group(3).upper(),
                    comparator=m.group(4),
                    value_pct=float(m.group(5)),
                    raw_fragment=clause_raw[:250],
                ))
                claim(m)
                found_here = True

        # Leftover pass: bare wavelengths adopt the NEXT function token in the
        # clause ("1176-1180HR 1064 808 885HT" -> 1064/808 belong to the HT).
        func_positions = [(fm.start(), fm.group(1).upper())
                          for fm in re.finditer(_FUNC, clause_raw, flags=re.IGNORECASE)]
        for m in re.finditer(_BAND, clause_raw):
            if not is_free(m):
                continue
            lo = float(m.group(1))
            hi = float(m.group(2)) if m.group(2) else lo
            if not (_wl_ok(lo) and _wl_ok(hi)):
                continue
            following = [f for pos, f in func_positions if pos >= m.end()]
            if following:
                out.bands.append(CoatingBand(
                    surface=surface, wl_min_nm=lo, wl_max_nm=hi,
                    function=following[0],
                    raw_fragment=clause_raw[:250],
                ))
                claim(m)
                found_here = True

        if not found_here and re.search(r"\d{3,4}", clause_raw):
            out.confidence = "partial"
            out.notes.append(f"unparsed: {clause_raw[:60]}")

    if not out.bands and norm.strip():
        out.confidence = "needs_review"
    return out


# --- geometry ---------------------------------------------------------------

@dataclass
class ParsedGeometry:
    roc_mm: float | None = None
    roc_is_flat: bool = False
    diameter_mm: float | None = None
    thickness_mm: float | None = None
    dimensions: str | None = None
    cut_angle_theta_deg: float | None = None
    cut_angle_phi_deg: float | None = None
    cut_axis: str | None = None
    doping_pct: float | None = None
    notes: list[str] = field(default_factory=list)


def parse_geometry(*cells: str) -> ParsedGeometry:
    """Extract geometry from the size / ROC / spec cells (joined, order-free)."""
    geo = ParsedGeometry()
    text = _normalize(" ".join(c for c in cells if c))

    m = re.search(r"R\s*=?\s*(-?\d+(?:\.\d+)?)\s*(?:mm)?", text)
    if m:
        geo.roc_mm = abs(float(m.group(1)))
    if "平镜" in text or "平面" in text:
        geo.roc_is_flat = True
        geo.roc_mm = None

    m = re.search(r"[DΦφ]\s*=?\s*(\d+(?:\.\d+)?)\s*mm", text)
    if m:
        geo.diameter_mm = float(m.group(1))

    m = re.search(r"厚度\s*(\d+(?:\.\d+)?)\s*mm", text)
    if m:
        geo.thickness_mm = float(m.group(1))

    m = re.search(r"(\d+(?:\.\d+)?)\s*[*×]\s*(\d+(?:\.\d+)?)\s*[*×]\s*(\d+(?:\.\d+)?)", text)
    if m:
        geo.dimensions = f"{m.group(1)}*{m.group(2)}*{m.group(3)}mm3"
        geo.thickness_mm = geo.thickness_mm or float(m.group(3))

    m = re.search(r"θ\s*=\s*(\d+(?:\.\d+)?)", text)
    if m:
        geo.cut_angle_theta_deg = float(m.group(1))
    m = re.search(r"φ\s*=\s*(\d+(?:\.\d+)?)", text)
    if m:
        geo.cut_angle_phi_deg = float(m.group(1))

    m = re.search(r"([a-cA-C])\s*-?\s*cut", text)
    if m:
        geo.cut_axis = f"{m.group(1).lower()}-cut"
    if "切向未知" in text:
        geo.cut_axis = None
        geo.notes.append("切向未知")

    m = re.search(r"掺杂浓度\s*(\d+(?:\.\d+)?)\s*at", text)
    if m:
        geo.doping_pct = float(m.group(1))
    else:
        m = re.search(r"(\d+(?:\.\d+)?)\s*%?\s*掺杂", text)
        if m:
            geo.doping_pct = float(m.group(1))

    return geo


def classify_category(name: str) -> str:
    """Coarse item category from its name."""
    n = (name or "").lower()
    if any(k in n for k in ("激光晶体", "增益")) or re.search(r"(nd|yb|er|tm)\s*[:：]", n):
        return "gain_crystal"
    if any(k in n.upper() for k in ("LBO", "KTP", "BBO", "BIBO", "KDP", "倍频晶体", "和频")):
        return "nonlinear_crystal"
    if "晶体" in n:
        return "crystal_other"
    if "透镜" in n or "lens" in n:
        return "lens"
    if "镜" in n or "mirror" in n:
        return "mirror"
    if "窗" in n or "window" in n:
        return "window"
    return "other"
