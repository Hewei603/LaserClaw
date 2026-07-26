"""ABCD ray/Gaussian-beam propagation and optical-resonator modes.

This is the ReZonator-class core: it computes cavity stability, the
self-consistent Gaussian eigenmode, and the beam radius at every element plane
of a linear resonator — the numbers the component-selection layer needs for
aperture-clipping and damage-fluence checks, and that a cavity-design tool
optimizes.

Clean-room implementation from standard paraxial optics (Kogelnik & Li,
*Proc. IEEE* 54, 1312 (1966); Siegman, *Lasers*).

Conventions (fixed across the module):

- Ray vector ``(y, y')`` with ``y`` the transverse position and ``y'`` the real
  ray slope ``dy/dz``.
- Distances in **millimetres**, beam radii ``w`` in millimetres, wavelength in
  **nanometres** (vacuum).
- Complex beam parameter ``q`` with ``1/q = 1/R - i lambda0 / (pi n w^2)``,
  ``lambda0`` the vacuum wavelength and ``n`` the local medium index.  ``q``
  propagates as ``q' = (A q + B)/(C q + D)``.
- A concave mirror / converging lens has **positive** focal length.  Mirror
  radius of curvature ``R > 0`` is concave (centre of curvature toward the
  beam); focal length ``f = R/2``.
- Free-space propagation uses physical length; a dielectric slab of index ``n``
  and thickness ``t`` in air reduces to an effective length ``t/n`` (standard).
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np


# --------------------------------------------------------------------------
# Element ABCD matrices
# --------------------------------------------------------------------------

def free_space(distance_mm: float) -> np.ndarray:
    """Propagation over a physical distance in a homogeneous medium."""
    return np.array([[1.0, float(distance_mm)], [0.0, 1.0]])


def thin_lens(focal_mm: float) -> np.ndarray:
    """Thin lens; positive focal length converges."""
    return np.array([[1.0, 0.0], [-1.0 / float(focal_mm), 1.0]])


def thermal_lens(focal_mm: float) -> np.ndarray:
    """Thermal lens in a gain medium (thin-lens equivalent, positive = focusing)."""
    return thin_lens(focal_mm)


def mirror_flat() -> np.ndarray:
    """Flat mirror (identity in the unfolded ABCD picture)."""
    return np.array([[1.0, 0.0], [0.0, 1.0]])


def mirror_curved(radius_mm: float, aoi_deg: float = 0.0, plane: str = "tangential") -> np.ndarray:
    """Curved mirror; ``radius_mm > 0`` concave (focusing), ``f = R/2``.

    At non-normal incidence the mirror is astigmatic: the effective radius is
    ``R*cos(theta)`` in the tangential plane and ``R/cos(theta)`` in the
    sagittal plane.
    """
    r = float(radius_mm)
    if aoi_deg:
        theta = np.deg2rad(aoi_deg)
        if plane == "tangential":
            r = r * np.cos(theta)
        elif plane == "sagittal":
            r = r / np.cos(theta)
        else:
            raise ValueError("plane must be 'tangential' or 'sagittal'")
    f = r / 2.0
    return thin_lens(f)


def interface_flat(n1: float, n2: float) -> np.ndarray:
    """Flat dielectric interface, medium n1 -> n2 (paraxial Snell)."""
    return np.array([[1.0, 0.0], [0.0, float(n1) / float(n2)]])


def interface_curved(radius_mm: float, n1: float, n2: float) -> np.ndarray:
    """Curved dielectric interface, radius R (>0 centre downstream), n1 -> n2."""
    r = float(radius_mm)
    n1 = float(n1)
    n2 = float(n2)
    return np.array([[1.0, 0.0], [(n1 - n2) / (n2 * r), n1 / n2]])


def slab(thickness_mm: float, n: float) -> np.ndarray:
    """A plane-parallel slab of index ``n`` immersed in air.

    Equivalent single matrix ``[[1, t/n], [0, 1]]`` (the well-known focal-shift
    result); the surrounding index is assumed 1 on both sides.
    """
    return np.array([[1.0, float(thickness_mm) / float(n)], [0.0, 1.0]])


def matrix(a: float, b: float, c: float, d: float) -> np.ndarray:
    """Arbitrary ABCD element."""
    return np.array([[float(a), float(b)], [float(c), float(d)]])


# --------------------------------------------------------------------------
# Element wrapper (for named, ordered systems and per-plane reporting)
# --------------------------------------------------------------------------

@dataclass
class Element:
    """A named ABCD element in an ordered optical system."""

    name: str
    M: np.ndarray
    n_after: float = 1.0  # refractive index of the medium *following* this element


# --------------------------------------------------------------------------
# Gaussian beam parameter helpers
# --------------------------------------------------------------------------

def q_from_beam(w_mm: float, radius_mm: float | None, wavelength_nm: float, n: float = 1.0) -> complex:
    """Complex beam parameter from spot size ``w`` and wavefront radius ``R``.

    ``radius_mm=None`` denotes a flat wavefront (a waist).
    """
    lam0_mm = wavelength_nm * 1e-6
    inv_R = 0.0 if radius_mm is None else 1.0 / float(radius_mm)
    inv_q = complex(inv_R, -lam0_mm / (np.pi * n * w_mm * w_mm))
    return 1.0 / inv_q


def w_from_q(q: complex, wavelength_nm: float, n: float = 1.0) -> float:
    """Beam radius ``w`` (1/e^2 amplitude) from the complex beam parameter."""
    lam0_mm = wavelength_nm * 1e-6
    imq = q.imag
    if imq <= 0:
        return float("nan")  # non-physical / diverging: caller should treat as unstable
    return float(np.sqrt(lam0_mm * (abs(q) ** 2) / (np.pi * n * imq)))


def radius_from_q(q: complex) -> float:
    """Wavefront radius of curvature ``R`` from ``q`` (inf at a waist)."""
    inv = (1.0 / q).real
    return float("inf") if inv == 0 else 1.0 / inv


def waist_from_q(q: complex, wavelength_nm: float, n: float = 1.0) -> tuple[float, float]:
    """Return ``(w0_mm, distance_to_waist_mm)`` for the mode described by ``q``.

    The waist is at ``z + Re(q)`` where ``q = (z - z_waist) + i z_R``; here we
    return the signed distance from the current plane to the waist and the waist
    radius.  ``distance > 0`` means the waist is downstream.

    The waist *size* ``w0`` is always physically correct.  The returned
    *distance* is a geometric length only in a single homogeneous medium; if a
    dielectric slab/interface lies between this plane and the waist it is a
    reduced (optical-path) length.  For systems containing intracavity media,
    use :func:`trace_beam` to locate the physical minimum-spot plane.
    """
    lam0_mm = wavelength_nm * 1e-6
    z_r = q.imag
    w0 = float(np.sqrt(lam0_mm * z_r / (np.pi * n)))
    distance_to_waist = -q.real
    return w0, distance_to_waist


def propagate_q(M: np.ndarray, q: complex) -> complex:
    """Apply an ABCD matrix to a complex beam parameter."""
    a, b = M[0, 0], M[0, 1]
    c, d = M[1, 0], M[1, 1]
    return (a * q + b) / (c * q + d)


# --------------------------------------------------------------------------
# System / resonator analysis
# --------------------------------------------------------------------------

def system_matrix(elements) -> np.ndarray:
    """Product of an ordered list of ABCD matrices or :class:`Element`.

    Ordered in the direction of propagation: the first element the light meets
    is applied first, so the product is ``M_last @ ... @ M_first``.
    """
    total = np.eye(2)
    for el in elements:
        m = el.M if isinstance(el, Element) else np.asarray(el, dtype=float)
        total = m @ total
    return total


def stability(M: np.ndarray) -> dict:
    """Stability of a round-trip ABCD matrix.

    Returns ``m = (A+D)/2``, a boolean ``stable`` (``|m| < 1``), and the
    equivalent ``g = m`` (so ``g1 g2 = (m+1)/2`` for a two-mirror cavity is *not*
    returned here — see :func:`two_mirror_cavity`).
    """
    m = 0.5 * (M[0, 0] + M[1, 1])
    return {"m": float(m), "stable": bool(abs(m) < 1.0), "marginal": bool(abs(abs(m) - 1.0) < 1e-9)}


def cavity_mode_q(M: np.ndarray) -> complex | None:
    """Self-consistent Gaussian eigen-``q`` of a round-trip matrix ``M``.

    Solves ``q = (A q + B)/(C q + D)`` -> ``C q^2 + (D-A) q - B = 0`` and returns
    the physical root with ``Im(q) > 0``.  Returns ``None`` if the cavity is
    unstable (real q / no confined mode) or ``C == 0``.
    """
    a = M[0, 0]
    c, d = M[1, 0], M[1, 1]
    if abs(c) < 1e-15:
        return None
    # (A+D)^2 - 4 = discriminant of C q^2 + (D-A) q - B = 0 (using det=1).
    disc = (a + d) ** 2 - 4.0
    if disc >= 0:
        return None  # unstable or marginal: no complex confined mode
    root = np.sqrt(complex(disc))  # imaginary
    q1 = ((a - d) + root) / (2.0 * c)
    q2 = ((a - d) - root) / (2.0 * c)
    q = q1 if q1.imag > 0 else q2
    return q if q.imag > 0 else None


def two_mirror_cavity(radius1_mm: float, radius2_mm: float, length_mm: float, wavelength_nm: float) -> dict:
    """Analyse a linear two-mirror resonator.

    Mirrors of radius ``R1``, ``R2`` (>0 concave) separated by ``length``.
    Returns g-parameters and the classical stability classification, plus the
    intracavity waist and the spot size on each mirror, all derived from the
    self-consistent Gaussian eigenmode of the round-trip matrix (singularity-free
    for any strictly stable cavity).

    The round trip starts and ends at mirror 1: ``free(L) -> M2 -> free(L) -> M1``.
    A confined Gaussian eigenmode exists only strictly inside the stability range
    ``0 < g1 g2 < 1``; at the boundaries (e.g. confocal, plane-parallel,
    concentric) the mode is marginal and waist/spots are ``nan``.
    """
    r1, r2, ell = float(radius1_mm), float(radius2_mm), float(length_mm)
    g1 = 1.0 - ell / r1
    g2 = 1.0 - ell / r2
    g1g2 = g1 * g2
    on_boundary = abs(g1g2) < 1e-12 or abs(g1g2 - 1.0) < 1e-12
    stable = 0.0 <= g1g2 <= 1.0
    out = {
        "g1": g1,
        "g2": g2,
        "g1g2": g1g2,
        "stable": bool(stable),
        "marginal": bool(stable and on_boundary),
        "length_mm": ell,
        "waist_w0_mm": float("nan"),
        "w_on_mirror1_mm": float("nan"),
        "w_on_mirror2_mm": float("nan"),
        "waist_from_mirror1_mm": float("nan"),
    }

    # Round-trip matrix at mirror 1 and its Gaussian eigenmode.
    round_trip = system_matrix([free_space(ell), mirror_curved(r2), free_space(ell), mirror_curved(r1)])
    q1 = cavity_mode_q(round_trip)
    if q1 is None:
        return out  # unstable or exactly marginal: no confined mode

    out["w_on_mirror1_mm"] = w_from_q(q1, wavelength_nm)
    q2 = propagate_q(free_space(ell), q1)
    out["w_on_mirror2_mm"] = w_from_q(q2, wavelength_nm)
    w0, dist = waist_from_q(q1, wavelength_nm)
    out["waist_w0_mm"] = w0
    out["waist_from_mirror1_mm"] = float(dist)
    return out


def trace_beam(elements, q_start: complex, wavelength_nm: float) -> list[dict]:
    """Propagate ``q_start`` through an ordered element list, reporting w at each plane.

    Returns a list of ``{name, w_mm, radius_mm, n}`` dicts, one entry per element
    (the beam parameter *after* that element).  ``n`` is ``Element.n_after``.
    """
    q = q_start
    trace = []
    for el in elements:
        m = el.M if isinstance(el, Element) else np.asarray(el, dtype=float)
        n_after = el.n_after if isinstance(el, Element) else 1.0
        q = propagate_q(m, q)
        trace.append(
            {
                "name": el.name if isinstance(el, Element) else "element",
                "w_mm": w_from_q(q, wavelength_nm, n_after),
                "radius_mm": radius_from_q(q),
                "n": n_after,
            }
        )
    return trace
