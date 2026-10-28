"""Second-moment caustic fit in air; mm and vacuum nm. No fabricated data."""
import math

import numpy as np


def fit_caustic(z_mm, radius_mm, wavelength_nm):
    z, w = np.asarray(z_mm, dtype=float), np.asarray(radius_mm, dtype=float)
    if z.ndim != 1 or z.size < 5 or w.shape != z.shape or not np.isfinite(z).all() or not np.isfinite(w).all() or np.any(w <= 0):
        raise ValueError("At least five finite z/radius pairs with positive radii are required")
    if len(np.unique(z)) < 5 or wavelength_nm <= 0:
        raise ValueError("Need five distinct positions and positive wavelength")
    origin = float(np.mean(z))
    a, b, c = np.polyfit(z-origin, w*w, 2)
    if a <= 0 or c-b*b/(4*a) <= 0:
        raise ValueError("Data do not support a physical caustic parabola")
    w0 = math.sqrt(c-b*b/(4*a))
    z0 = origin-b/(2*a)
    theta = math.sqrt(a)
    m2 = math.pi*w0*theta/(wavelength_nm*1e-6)
    predicted = a*(z-origin)**2+b*(z-origin)+c
    denom = float(np.sum((w*w-np.mean(w*w))**2))
    r2 = 1-float(np.sum((w*w-predicted)**2))/denom if denom > 0 else None
    warnings = []
    if not min(z) < z0 < max(z):
        warnings.append("Fitted waist is outside sampled range; measure both sides of focus before using it as an installation target.")
    if m2 < 1:
        warnings.append("Inferred M² < 1: check radius/diameter convention, wavelength, calibration and noise; do not silently clamp to 1.")
    if r2 is None or r2 < .98:
        warnings.append("Weak quadratic fit; inspect raw profiles and outliers.")
    return {"waist_z_mm": float(z0), "waist_radius_mm": w0, "divergence_half_angle_rad": theta, "m2": m2,
            "rayleigh_equivalent_mm": w0/theta, "r_squared_w2": r2, "warnings": warnings,
            "data": {"z_mm": z.tolist(), "radius_mm": w.tolist(), "fit_radius_mm": np.sqrt(predicted).tolist()},
            "scope": "Air, paraxial second-moment propagation. M² interpretation requires consistent second-moment radii; a Gaussian 1/e² fit is only equivalent for Gaussian profiles. This fit alone is not ISO certification."}
