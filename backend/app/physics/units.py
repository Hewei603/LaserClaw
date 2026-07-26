"""Unit conventions and converters for the physics kernel.

Conventions (uniform across the package — see each module docstring):

- Public APIs name their units in the argument (``wavelength_nm``, ``length_m``,
  ``aoi_deg``) so a caller can never be confused about what to pass.
- Wavelengths: nanometres in public APIs; Sellmeier evaluation uses micrometres
  internally (the standard form of published coefficients).
- Beam / cavity optics (``beam.py``): geometric lengths, ROC and beam radii in
  **millimetres**.
- Thin-film layer thicknesses (``tmm.py``): nanometres (industry convention).
- Angles: degrees in public APIs, radians internally.

The converters below are general SI helpers (they convert *to metres* / radians
from a named unit); the physics modules state their own working units above and
do not require callers to pre-convert to metres.
"""
from __future__ import annotations

import math

# --- length -> metres -------------------------------------------------------

def nm(value: float) -> float:
    """Nanometres -> metres."""
    return value * 1e-9


def um(value: float) -> float:
    """Micrometres -> metres."""
    return value * 1e-6


def mm(value: float) -> float:
    """Millimetres -> metres."""
    return value * 1e-3


def cm(value: float) -> float:
    """Centimetres -> metres."""
    return value * 1e-2


# --- metres -> named unit ---------------------------------------------------

def to_nm(value_m: float) -> float:
    return value_m * 1e9


def to_um(value_m: float) -> float:
    return value_m * 1e6


def to_mm(value_m: float) -> float:
    return value_m * 1e3


# --- wavelength helpers -----------------------------------------------------

def nm_to_um(wavelength_nm: float) -> float:
    """Wavelength nm -> um (Sellmeier evaluation unit)."""
    return wavelength_nm * 1e-3


# --- angles -----------------------------------------------------------------

def deg2rad(angle_deg: float) -> float:
    return math.radians(angle_deg)


def rad2deg(angle_rad: float) -> float:
    return math.degrees(angle_rad)
