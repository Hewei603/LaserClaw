"""Birefringent phase matching for three-wave mixing (SHG / SFG).

Computes critical (angle-tuned) phase-matching angles, spatial walk-off, and
angular acceptance for negative/positive **uniaxial** crystals (e.g. BBO) and
for propagation in a **principal plane** of a **biaxial** crystal (e.g. LBO,
KTP), where the problem reduces to an effective-uniaxial one.

Convention: all wavelengths are vacuum wavelengths in **nanometres**.  A mixing
process ``lambda1 + lambda2 -> lambda3`` conserves energy
``1/lambda3 = 1/lambda1 + 1/lambda2`` (SHG is ``lambda1 = lambda2 = 2*lambda3``).
Phase matching requires ``n3/lambda3 = n1/lambda1 + n2/lambda2``.

Polarization labels use ``o`` (ordinary) / ``e`` (extraordinary) for uniaxial
and for principal-plane biaxial (the "slow"/"fast" eigenpolarizations).

Reference: Dmitriev, Gurzadyan & Nikogosyan, *Handbook of Nonlinear Optical
Crystals*; Boyd, *Nonlinear Optics*.  Clean-room implementation.
"""
from __future__ import annotations

import math
from dataclasses import dataclass

from .materials import n_real

# Registry of crystals this module knows how to phase-match, mapping a crystal
# name to its optic class and the material keys for its principal indices.
_UNIAXIAL = {
    # negative uniaxial: n_e < n_o
    "bbo": {"o": "bbo_o", "e": "bbo_e", "sign": "negative"},
}
_BIAXIAL = {
    # principal indices n_x < n_y < n_z
    "lbo": {"x": "lbo_x", "y": "lbo_y", "z": "lbo_z"},
    "ktp": {"x": "ktp_x", "y": "ktp_y", "z": "ktp_z"},
    "bibo": {"x": "bibo_x", "y": "bibo_y", "z": "bibo_z"},
}


def energy_conserving_third(lambda1_nm: float, lambda2_nm: float) -> float:
    """Return lambda3 for ``1/lambda3 = 1/lambda1 + 1/lambda2``."""
    return 1.0 / (1.0 / lambda1_nm + 1.0 / lambda2_nm)


# --------------------------------------------------------------------------
# Uniaxial
# --------------------------------------------------------------------------

def n_e_theta(n_o: float, n_e: float, theta_rad: float) -> float:
    """Angle-dependent extraordinary index of a uniaxial crystal."""
    c = math.cos(theta_rad)
    s = math.sin(theta_rad)
    return 1.0 / math.sqrt((c * c) / (n_o * n_o) + (s * s) / (n_e * n_e))


def _uniaxial_index(crystal: str, wavelength_nm: float, pol: str, theta_rad: float) -> float:
    keys = _UNIAXIAL[crystal]
    n_o = n_real(keys["o"], wavelength_nm)
    if pol == "o":
        return n_o
    n_e = n_real(keys["e"], wavelength_nm)
    return n_e_theta(n_o, n_e, theta_rad)


def _bisect(f, lo: float, hi: float, tol: float = 1e-12, max_iter: int = 200) -> float | None:
    """Simple bracketed bisection root finder (numpy-free, deterministic)."""
    flo, fhi = f(lo), f(hi)
    if flo == 0.0:
        return lo
    if fhi == 0.0:
        return hi
    if flo * fhi > 0:
        return None
    for _ in range(max_iter):
        mid = 0.5 * (lo + hi)
        fm = f(mid)
        if abs(fm) < tol or (hi - lo) < tol:
            return mid
        if flo * fm < 0:
            hi, fhi = mid, fm
        else:
            lo, flo = mid, fm
    return 0.5 * (lo + hi)


@dataclass
class PhaseMatch:
    crystal: str
    process: str            # "SHG" | "SFG"
    type: str               # "I" | "II"
    theta_deg: float | None
    phi_deg: float | None
    plane: str | None
    lambda1_nm: float
    lambda2_nm: float
    lambda3_nm: float
    walkoff_mrad: float | None
    delta_theta_int_mrad_cm: float | None  # internal angular acceptance * length
    confidence: str
    notes: str


def _walkoff_uniaxial(n_o: float, n_e: float, theta_rad: float) -> float:
    """Spatial walk-off angle (rad) of the e-ray at angle theta."""
    ne_t = n_e_theta(n_o, n_e, theta_rad)
    return abs(math.atan(ne_t * ne_t * (1.0 / (n_e * n_e) - 1.0 / (n_o * n_o)) * math.sin(theta_rad) * math.cos(theta_rad)))


# Candidate polarization assignments (pol1, pol2, pol3) tried for each type.  We
# try both crystal signs (which of the fundamental/harmonic is the tuned ray) so
# negative- and positive-birefringence phase matches are both found.
_TYPE_ASSIGNMENTS = {
    "I": [("o", "o", "e"), ("e", "e", "o")],
    "II": [("o", "e", "e"), ("e", "o", "e"), ("e", "o", "o"), ("o", "e", "o")],
}


def _solve_pm(n_pol, l1: float, l2: float, l3: float, pm_type: str):
    """Find (angle_rad, assignment) that phase-matches, trying all pairings.

    ``n_pol(wavelength_nm, pol, angle_rad)`` returns the index of polarization
    ``pol`` ('o'|'e') at that angle.  Returns ``(None, None)`` if no pairing
    phase-matches in (0, 90) deg.
    """
    for assign in _TYPE_ASSIGNMENTS[pm_type]:
        p1, p2, p3 = assign

        def f(ang, p1=p1, p2=p2, p3=p3):
            return n_pol(l3, p3, ang) / l3 - (n_pol(l1, p1, ang) / l1 + n_pol(l2, p2, ang) / l2)

        ang = _bisect(f, math.radians(0.001), math.radians(89.999))
        if ang is not None:
            return ang, assign
    return None, None


def phase_match_uniaxial(
    crystal: str,
    lambda1_nm: float,
    lambda2_nm: float | None = None,
    pm_type: str = "I",
) -> PhaseMatch:
    """Critical phase-matching angle for a uniaxial crystal (negative-uniaxial types).

    ``lambda2_nm=None`` -> SHG (``lambda1 = lambda2``).  Type I is ``o o -> e``;
    Type II is ``o e -> e`` (negative uniaxial).  Returns theta (from optic axis)
    and walk-off.  Raises ``KeyError`` for an unknown crystal.
    """
    crystal = crystal.lower()
    if crystal not in _UNIAXIAL:
        raise KeyError(f"'{crystal}' is not a registered uniaxial crystal ({list(_UNIAXIAL)})")
    if pm_type not in ("I", "II"):
        raise ValueError("pm_type must be 'I' or 'II'")
    process = "SHG" if lambda2_nm is None else "SFG"
    l1 = lambda1_nm
    l2 = lambda1_nm if lambda2_nm is None else lambda2_nm
    l3 = energy_conserving_third(l1, l2)

    def n_pol(wl, pol, ang):
        return _uniaxial_index(crystal, wl, pol, ang)

    theta, assign = _solve_pm(n_pol, l1, l2, l3, pm_type)
    if theta is None:
        return PhaseMatch(crystal, process, pm_type, None, None, None, l1, l2, l3, None, None,
                          "high", "No angle phase-matching solution in (0,90) deg for this configuration.")

    # Walk-off of whichever mixing waves are extraordinary (report the harmonic's).
    keys = _UNIAXIAL[crystal]
    walkoff = None
    if assign[2] == "e":
        walkoff = _walkoff_uniaxial(n_real(keys["o"], l3), n_real(keys["e"], l3), theta) * 1e3
    return PhaseMatch(
        crystal=crystal, process=process, type=pm_type,
        theta_deg=math.degrees(theta), phi_deg=None, plane=None,
        lambda1_nm=l1, lambda2_nm=l2, lambda3_nm=l3,
        walkoff_mrad=walkoff, delta_theta_int_mrad_cm=None,
        confidence="high",
        notes=f"Uniaxial type {pm_type} {process}, pol {''.join(assign)}; theta from optic axis. "
              f"Walk-off reported for the extraordinary harmonic only.",
    )


# --------------------------------------------------------------------------
# Biaxial (principal-plane reduction)
# --------------------------------------------------------------------------

def _biaxial_plane_indices(crystal: str, wavelength_nm: float, plane: str):
    """Return (n_slow_const, n_x_or_y_pair) principal indices used in a plane.

    For propagation in a principal plane of a biaxial crystal, one eigenwave is
    polarized normal to the plane (constant index = the third principal index)
    and the other is polarized in-plane.  The in-plane wave's polarization is
    perpendicular to k (also in the plane), so at propagation angle 0 (k along
    the first listed axis) the in-plane polarization lies along the *second*
    axis.  The returned pair is therefore ``(n_at_angle0, n_at_angle90)`` with
    that perpendicular geometry already applied.
    """
    keys = _BIAXIAL[crystal]
    nx = n_real(keys["x"], wavelength_nm)
    ny = n_real(keys["y"], wavelength_nm)
    nz = n_real(keys["z"], wavelength_nm)
    if plane == "xy":
        # angle phi from X; k along X (phi=0) -> in-plane pol along Y -> n_y.
        return nz, (ny, nx)
    if plane == "xz":
        # angle theta from Z; k along Z (theta=0) -> in-plane pol along X -> n_x.
        return ny, (nx, nz)
    if plane == "yz":
        # angle theta from Z; k along Z (theta=0) -> in-plane pol along Y -> n_y.
        return nx, (ny, nz)
    raise ValueError("plane must be 'xy', 'xz' or 'yz'")


def _inplane_index(n_a: float, n_b: float, ang_rad: float) -> float:
    """In-plane index at angle ``ang_rad`` measured from the axis of index ``n_a``.

    Ellipse interpolation: 1/n^2 = cos^2/n_a^2 + sin^2/n_b^2.
    """
    c = math.cos(ang_rad)
    s = math.sin(ang_rad)
    return 1.0 / math.sqrt((c * c) / (n_a * n_a) + (s * s) / (n_b * n_b))


def phase_match_biaxial_plane(
    crystal: str,
    plane: str,
    lambda1_nm: float,
    lambda2_nm: float | None = None,
    pm_type: str = "I",
) -> PhaseMatch:
    """Critical phase matching for propagation in a biaxial principal plane.

    Reduces to an effective-uniaxial problem: the out-of-plane ("slow", constant)
    index plays the role of one polarization and the in-plane (angle-varying)
    index the other.  Returns the in-plane angle (reported as ``phi`` measured
    from the first in-plane principal axis) for the requested type.

    This is the standard principal-plane approximation and is marked
    ``confidence='medium'``; it is validated against published crystals in the
    test suite.  Off-principal-plane (fully biaxial) matching is out of scope.
    """
    crystal = crystal.lower()
    if crystal not in _BIAXIAL:
        raise KeyError(f"'{crystal}' is not a registered biaxial crystal ({list(_BIAXIAL)})")
    process = "SHG" if lambda2_nm is None else "SFG"
    l1 = lambda1_nm
    l2 = lambda1_nm if lambda2_nm is None else lambda2_nm
    l3 = energy_conserving_third(l1, l2)

    def const_and_pair(wl):
        return _biaxial_plane_indices(crystal, wl, plane)

    if pm_type not in ("I", "II"):
        raise ValueError("pm_type must be 'I' or 'II'")

    # Effective "ordinary" = out-of-plane constant index; "extraordinary" = in-plane varying.
    def n_pol(wl, pol, ang):
        const, (na, nb) = const_and_pair(wl)
        if pol == "o":
            return const
        return _inplane_index(na, nb, ang)

    # Try all pairings (both which-wave-is-in-plane and both birefringence signs).
    ang, assign = _solve_pm(n_pol, l1, l2, l3, pm_type)
    if ang is None:
        return PhaseMatch(crystal, process, pm_type, None, None, plane, l1, l2, l3, None, None,
                          "medium", f"No in-plane phase-matching solution in {plane} plane for type {pm_type}.")

    # Report as (theta, phi): xy plane -> theta=90, phi=angle; xz -> phi=0/180 theta; yz -> phi=90.
    ang_deg = math.degrees(ang)
    if plane == "xy":
        theta_deg, phi_deg = 90.0, ang_deg
    elif plane == "xz":
        theta_deg, phi_deg = ang_deg, 0.0
    else:  # yz
        theta_deg, phi_deg = ang_deg, 90.0

    return PhaseMatch(
        crystal=crystal, process=process, type=pm_type,
        theta_deg=theta_deg, phi_deg=phi_deg, plane=plane,
        lambda1_nm=l1, lambda2_nm=l2, lambda3_nm=l3,
        walkoff_mrad=None, delta_theta_int_mrad_cm=None,
        confidence="medium",
        notes=f"Biaxial {plane}-plane principal-plane approximation, type {pm_type} {process}, "
              f"pol {''.join(assign)}. Walk-off not reported for biaxial cuts.",
    )
