"""Thin-film transfer-matrix (characteristic-matrix / Abeles) solver.

Computes reflectance ``R``, transmittance ``T`` and absorptance ``A`` of a
stratified isotropic multilayer coating on a semi-infinite substrate, for any
angle of incidence and s/p polarization, with dispersive (and optionally lossy)
layer indices.

Physics reference: Born & Wolf, *Principles of Optics*, and H. A. Macleod,
*Thin-Film Optical Filters* (characteristic matrix in tilted-admittance form).
Clean-room implementation from the published formulation.

Sign convention: complex index ``n - i k`` with ``k >= 0`` for loss; the
physical branch of ``cos(theta)`` is enforced so evanescent/lossy waves decay
into the medium.

Length units: layer thicknesses and wavelength in **nanometres** (they appear
only as the ratio ``d/lambda`` inside the phase, so any consistent unit works).
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

from .materials import index_of


@dataclass
class Layer:
    """One coating layer.

    Provide either a material name (resolved through the dispersion engine at the
    query wavelength) or a fixed complex index ``n`` (n - i k).  ``thickness_nm``
    is the physical thickness.
    """

    thickness_nm: float
    material: str | None = None
    n: complex | None = None

    def index_at(self, wavelength_nm: float) -> complex:
        if self.material is not None:
            return index_of(self.material, wavelength_nm)
        if self.n is not None:
            return complex(self.n)
        raise ValueError("Layer needs either a material name or an explicit index n")


@dataclass
class Stack:
    """A coating: incident medium, ordered layers (incident side first), substrate."""

    layers: list[Layer] = field(default_factory=list)
    incident: str = "air"
    substrate: str = "fused_silica"

    def incident_index(self, wavelength_nm: float) -> complex:
        return index_of(self.incident, wavelength_nm)

    def substrate_index(self, wavelength_nm: float) -> complex:
        return index_of(self.substrate, wavelength_nm)


def _cos_theta(n: complex, n0_sin0: complex) -> complex:
    """Physical-branch cos(theta) in a medium of index ``n = n' - i n''``.

    ``n0_sin0 = n_incident * sin(theta_incident)`` is conserved (Snell).  With
    the ``n - ik`` convention the physical (forward) branch is fixed by
    **forward power flow**: ``Re(n*cos) >= 0``, using ``Im(n*cos) >= 0`` only as
    a tie-break when ``Re`` vanishes (the evanescent / total-internal-reflection
    case, where the transmitted wave must decay into the medium).
    """
    n = complex(n)
    sin2 = (n0_sin0 / n) ** 2
    cos = np.sqrt(1.0 - sin2)
    ncos = n * cos
    if ncos.real < -1e-12 or (abs(ncos.real) < 1e-12 and ncos.imag < 0):
        cos = -cos
    return cos


def _admittance(n: complex, cos_theta: complex, pol: str) -> complex:
    """Tilted optical admittance in free-space-cancelled units (n*cos or n/cos)."""
    if pol == "s":
        return n * cos_theta
    if pol == "p":
        return n / cos_theta
    raise ValueError("pol must be 's' or 'p'")


def solve_RT(
    layers_n: np.ndarray,
    layers_d_nm: np.ndarray,
    wavelength_nm: float,
    aoi_deg: float,
    pol: str,
    n_incident: complex,
    n_substrate: complex,
) -> tuple[float, float, float]:
    """Core single-wavelength single-polarization solve.

    Returns ``(R, T, A)`` with ``A = 1 - R - T``.

    Assumes a **lossless incident medium** (the closed-form ``R = |r|^2`` and
    ``T = 4 Re(eta0) Re(eta_s)/|eta0 B + C|^2`` are exact only then; here the
    incident medium is always air/vacuum).  The substrate and layers may be
    lossy.  At exactly grazing incidence (90 deg) the physical limit ``R=1,
    T=0`` is returned to avoid the ``n/cos`` singularity for p-polarization.

    Parameters use raw arrays so this stays a tight numeric kernel; higher-level
    callers use :func:`spectrum` / the coating tool.
    """
    if pol not in ("s", "p"):
        raise ValueError("pol must be 's' or 'p'")

    n0 = complex(n_incident)
    ns = complex(n_substrate)
    theta0 = np.deg2rad(aoi_deg)
    if abs(np.cos(theta0)) < 1e-12:
        return 1.0, 0.0, 0.0  # grazing incidence: total reflection in the paraxial limit
    n0_sin0 = n0 * np.sin(theta0)

    cos0 = _cos_theta(n0, n0_sin0)
    coss = _cos_theta(ns, n0_sin0)
    eta0 = _admittance(n0, cos0, pol)
    etas = _admittance(ns, coss, pol)

    # Characteristic matrix of the stack (product of layer matrices).
    m = np.eye(2, dtype=complex)
    two_pi = 2.0 * np.pi
    for n_layer, d_nm in zip(layers_n, layers_d_nm):
        n_layer = complex(n_layer)
        cosj = _cos_theta(n_layer, n0_sin0)
        etaj = _admittance(n_layer, cosj, pol)
        delta = two_pi * n_layer * d_nm * cosj / wavelength_nm
        cd = np.cos(delta)
        sd = np.sin(delta)
        mj = np.array(
            [[cd, 1j * sd / etaj], [1j * etaj * sd, cd]],
            dtype=complex,
        )
        m = m @ mj

    # [B, C]^T = M @ [1, eta_s]^T
    b = m[0, 0] + m[0, 1] * etas
    c = m[1, 0] + m[1, 1] * etas

    denom = eta0 * b + c
    r = (eta0 * b - c) / denom
    R = float(np.abs(r) ** 2)
    # Transmittance into a (possibly lossy) substrate.
    T = float(4.0 * eta0.real * etas.real / (np.abs(denom) ** 2))
    A = 1.0 - R - T
    return R, T, A


def _resolve_indices(stack: Stack, wavelength_nm: float) -> tuple[np.ndarray, np.ndarray, complex, complex]:
    layers_n = np.array([ly.index_at(wavelength_nm) for ly in stack.layers], dtype=complex)
    layers_d = np.array([ly.thickness_nm for ly in stack.layers], dtype=float)
    n0 = stack.incident_index(wavelength_nm)
    ns = stack.substrate_index(wavelength_nm)
    return layers_n, layers_d, n0, ns


def solve_stack(stack: Stack, wavelength_nm: float, aoi_deg: float = 0.0, pol: str = "avg") -> dict:
    """Solve one wavelength for a :class:`Stack`.

    ``pol`` may be ``'s'``, ``'p'`` or ``'avg'`` (unpolarized mean).  Returns a
    dict with ``R``, ``T``, ``A`` (and per-polarization values when ``avg``).
    """
    layers_n, layers_d, n0, ns = _resolve_indices(stack, wavelength_nm)

    def one(p: str) -> tuple[float, float, float]:
        return solve_RT(layers_n, layers_d, wavelength_nm, aoi_deg, p, n0, ns)

    if pol in ("s", "p"):
        R, T, A = one(pol)
        return {"R": R, "T": T, "A": A, "pol": pol}
    if pol == "avg":
        rs, ts, as_ = one("s")
        rp, tp, ap = one("p")
        return {
            "R": 0.5 * (rs + rp),
            "T": 0.5 * (ts + tp),
            "A": 0.5 * (as_ + ap),
            "R_s": rs,
            "R_p": rp,
            "T_s": ts,
            "T_p": tp,
            "pol": "avg",
        }
    raise ValueError("pol must be 's', 'p' or 'avg'")


def spectrum(
    stack: Stack,
    wl_grid_nm: np.ndarray,
    aoi_deg: float = 0.0,
    pol: str = "avg",
) -> dict:
    """R/T/A over a wavelength grid.  Returns arrays keyed ``wl_nm``, ``R``, ``T``, ``A``."""
    wl = np.asarray(wl_grid_nm, dtype=float)
    R = np.empty_like(wl)
    T = np.empty_like(wl)
    A = np.empty_like(wl)
    for i, w in enumerate(wl):
        res = solve_stack(stack, float(w), aoi_deg=aoi_deg, pol=pol)
        R[i], T[i], A[i] = res["R"], res["T"], res["A"]
    return {"wl_nm": wl, "R": R, "T": T, "A": A}
