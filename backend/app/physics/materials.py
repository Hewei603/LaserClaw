"""Refractive-index dispersion engine.

Evaluates a material's complex refractive index ``n - i k`` at a given
wavelength from a bundled, offline dispersion snapshot (``data/materials.json``).

All published dispersion formulas here use wavelength in **micrometres**; public
APIs take **nanometres** and convert internally.

Supported models (see ``data/materials.json`` ``_meta.models``):

- ``sellmeier_b``   : n^2 = 1 + sum_i B_i L2 / (L2 - C_i)
- ``sellmeier_a``   : n^2 = A + B/(L2 - C) - D L2 (+ E L2^2 if E given)
- ``sellmeier_a_plus``: n^2 = A + sum_j Bj L2 / (L2 - Cj)
- ``sellmeier_yag`` : n^2 = 1 + B1 L2/(L2 - C1) + B2 L2/(L2 - C2)
- ``cauchy``        : n = A + B / L2
- ``constant``      : n = value

where ``L2 = lambda_um^2``.

Uncertainty is explicit: :func:`index_info` reports an ``in_range`` flag and the
material's ``confidence`` and never raises.  :func:`index_of` evaluates the raw
formula and will raise ``ValueError`` if a query falls on/beyond a Sellmeier pole
(where ``n**2 < 0``); callers that may probe far out of range should prefer
:func:`index_info`, which returns ``nan`` with ``in_range=False`` instead.
"""
from __future__ import annotations

import json
import math
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

_DATA_PATH = Path(__file__).resolve().parent / "data" / "materials.json"


@lru_cache(maxsize=1)
def load_materials() -> dict:
    """Load and cache the bundled dispersion snapshot."""
    with open(_DATA_PATH, encoding="utf-8") as fh:
        return json.load(fh)


@lru_cache(maxsize=1)
def _alias_map() -> dict:
    """Map lowercase aliases -> canonical material key."""
    data = load_materials()
    amap: dict[str, str] = {}
    for key, entry in data.items():
        if key.startswith("_"):
            continue
        amap[key.lower()] = key
        for alias in entry.get("aliases", []):
            amap[alias.lower()] = key
    return amap


class MaterialError(KeyError):
    """Raised when a material name is unknown."""


def resolve_material(name: str) -> str:
    """Return the canonical material key for a name or alias (case-insensitive)."""
    key = _alias_map().get(str(name).strip().lower())
    if key is None:
        available = ", ".join(sorted(k for k in load_materials() if not k.startswith("_")))
        raise MaterialError(f"Unknown material '{name}'. Available: {available}")
    return key


def _n_real_from_model(entry: dict, lambda_um: float) -> float:
    model = entry["model"]
    l2 = lambda_um * lambda_um

    if model == "constant":
        return float(entry["value"])

    if model == "cauchy":
        return float(entry["A"] + entry["B"] / l2)

    if model == "sellmeier_b":
        n2 = 1.0
        for b, c in zip(entry["B"], entry["C"]):
            n2 += b * l2 / (l2 - c)
        return math.sqrt(n2)

    if model == "sellmeier_yag":
        n2 = 1.0 + entry["B1"] * l2 / (l2 - entry["C1"]) + entry["B2"] * l2 / (l2 - entry["C2"])
        return math.sqrt(n2)

    if model == "sellmeier_a":
        n2 = entry["A"] + entry["B"] / (l2 - entry["C"]) - entry["D"] * l2
        if "E" in entry:
            n2 += entry["E"] * l2 * l2
        return math.sqrt(n2)

    if model == "sellmeier_a_plus":
        n2 = entry["A"]
        for b, c in entry["terms"]:
            n2 += b * l2 / (l2 - c)
        return math.sqrt(n2)

    raise ValueError(f"Unsupported dispersion model '{model}'")


def index_of(material: str, wavelength_nm: float) -> complex:
    """Complex refractive index ``n - i k`` of *material* at *wavelength_nm*.

    ``k`` is taken as the (currently constant) absorption index from the data
    file; a positive ``k`` denotes loss with the ``n - ik`` sign convention used
    by the TMM solver.
    """
    entry = load_materials()[resolve_material(material)]
    lambda_um = wavelength_nm * 1e-3
    n_real = _n_real_from_model(entry, lambda_um)
    k = float(entry.get("k", 0.0))
    return complex(n_real, -k)


def n_real(material: str, wavelength_nm: float) -> float:
    """Real part of the refractive index (convenience wrapper)."""
    return index_of(material, wavelength_nm).real


@dataclass(frozen=True)
class IndexInfo:
    material: str
    wavelength_nm: float
    n: float
    k: float
    in_range: bool
    confidence: str
    source: str


def index_info(material: str, wavelength_nm: float) -> IndexInfo:
    """Return the index plus provenance / validity metadata for honest reporting.

    Never raises: the ``in_range`` flag is determined from the declared range
    *before* evaluating, and if the dispersion formula fails (out past a
    Sellmeier pole) ``n``/``k`` come back as ``nan`` rather than propagating the
    exception.
    """
    key = resolve_material(material)
    entry = load_materials()[key]
    lambda_um = wavelength_nm * 1e-3
    lo, hi = entry.get("valid_range_um", [0.0, math.inf])
    in_range = lo <= lambda_um <= hi
    try:
        val = index_of(material, wavelength_nm)
        n, k = val.real, -val.imag
    except (ValueError, ZeroDivisionError):
        n = k = float("nan")
    return IndexInfo(
        material=key,
        wavelength_nm=wavelength_nm,
        n=n,
        k=k,
        in_range=in_range,
        confidence=entry.get("confidence", "unknown"),
        source=entry.get("source", ""),
    )


def available_materials() -> list[str]:
    """Sorted list of canonical material keys."""
    return sorted(k for k in load_materials() if not k.startswith("_"))
