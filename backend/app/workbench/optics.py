"""General ordered paraxial systems. No experiment-specific topology selection.

Elements use reduced q=q_physical/n; each dielectric segment has flat faces.
Standing-wave systems are unfolded automatically; ring systems specify one full
round trip. Coplanar T/S planes only, no rotated astigmatism or nonparaxial solve.
"""
from __future__ import annotations

import math
from typing import Literal

import numpy as np
from pydantic import BaseModel, ConfigDict, Field, model_validator

from ..physics import beam as B

SCAN_PARAMETERS = {"space": {"length_mm", "n"}, "lens": {"focal_mm"}, "mirror": {"radius_mm", "aoi_deg"},
                   "thick_lens": {"length_mm", "n", "front_radius_mm", "back_radius_mm"},
                   "grin": {"length_mm", "n", "gradient_per_mm"}, "matrix": set()}


class StrictInput(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)


class OpticalElement(StrictInput):
    uid: str = Field(default="", max_length=100, description="Stable project element identity; preserve on edit.")
    name: str = Field(min_length=1, max_length=100)
    kind: Literal["space", "lens", "mirror", "thick_lens", "grin", "matrix"]
    length_mm: float = Field(default=0, ge=0, le=1e6)
    n: float = Field(default=1, ge=1, le=5, description="Flat-faced medium index for a space segment; all thin elements use air-equivalent power.")
    focal_mm: float | None = Field(default=None, description="Signed air-equivalent focal length; positive converges.")
    radius_mm: float | None = Field(default=None, description="Mirror radius; null flat, positive concave, negative convex.")
    aoi_deg: float = Field(default=0, ge=0, lt=85)
    front_radius_mm: float | None = Field(default=None, description="Thick lens first surface: positive center downstream, null flat.")
    back_radius_mm: float | None = Field(default=None, description="Thick lens second surface: positive center downstream, null flat.")
    gradient_per_mm: float = Field(default=0, ge=0, le=10, description="Focusing quadratic GRIN coefficient g; n(r) approximately n0*(1-g²r²/2).")
    matrix_t: list[float] | None = Field(default=None, min_length=4, max_length=4, description="A,B,C,D in reduced (y,n*theta), determinant 1. B mm, C 1/mm.")
    matrix_s: list[float] | None = Field(default=None, min_length=4, max_length=4)

    @model_validator(mode="after")
    def physical(self):
        if self.kind == "lens" and (self.focal_mm is None or abs(self.focal_mm) < 1e-6):
            raise ValueError("Lens focal_mm must be nonzero")
        if self.kind == "mirror" and self.radius_mm is not None and abs(self.radius_mm) < 1e-6:
            raise ValueError("Mirror radius_mm must be nonzero or null (flat)")
        if self.kind in {"lens", "mirror", "matrix"} and (self.length_mm != 0 or self.n != 1):
            raise ValueError("Thin elements have zero length and use air-equivalent power; model media as separate space segments")
        if self.kind in {"thick_lens", "grin"} and self.length_mm <= 0:
            raise ValueError("Thick/GRIN element requires positive physical length")
        if self.front_radius_mm == 0 or self.back_radius_mm == 0:
            raise ValueError("Flat refracting surface radius is null, not zero")
        if self.kind == "matrix":
            if self.matrix_t is None:
                raise ValueError("Custom element requires matrix_t")
            for values in (self.matrix_t, self.matrix_s):
                if values is not None and not math.isclose(values[0]*values[3]-values[1]*values[2], 1, abs_tol=1e-8):
                    raise ValueError("Reduced real lossless ABCD determinant must be 1")
        return self


class OpticalSystem(StrictInput):
    mode: Literal["single_pass", "standing_wave", "ring"]
    wavelength_nm: float = Field(gt=0, le=1e6)
    elements: list[OpticalElement] = Field(min_length=1, max_length=80)
    input_radius_mm: float | None = Field(default=None, gt=0, description="1/e² intensity radius at the input plane, for single_pass only.")
    input_curvature_mm: float | None = Field(default=None, description="Wavefront curvature at input; null denotes waist. Air on input plane.")
    samples_per_segment: int = Field(default=40, ge=2, le=150)
    beam_quality_m2: float = Field(default=1, ge=1, le=10000, description="Single-pass second-moment/equivalent Gaussian M²; cavity eigenmode always M²=1.")

    @model_validator(mode="after")
    def topology(self):
        if self.input_curvature_mm == 0:
            raise ValueError("Flat input wavefront is null, not zero curvature radius")
        if self.mode == "single_pass" and self.input_radius_mm is None:
            raise ValueError("Single pass requires input beam radius and wavefront (null for waist)")
        if self.mode != "single_pass" and self.beam_quality_m2 != 1:
            raise ValueError("Resonator eigenmode is fundamental; M²>1 is only a single-pass propagation surrogate")
        if self.mode == "standing_wave" and (len(self.elements) < 3 or self.elements[0].kind != "mirror" or self.elements[-1].kind != "mirror"):
            raise ValueError("Standing-wave list must start and end with a mirror, with the one-way path between them")
        if sum(e.length_mm for e in self.elements) <= 0:
            raise ValueError("System must contain positive propagation length")
        return self


class OpticalScan(StrictInput):
    system: OpticalSystem
    element_index: int = Field(ge=0)
    parameter: Literal["length_mm", "focal_mm", "radius_mm", "n", "aoi_deg", "front_radius_mm", "back_radius_mm", "gradient_per_mm"]
    start: float
    stop: float
    count: int = Field(default=101, ge=2, le=501)


class ScanAxis(StrictInput):
    element_index: int = Field(ge=0)
    parameter: str
    start: float
    stop: float
    count: int = Field(default=41, ge=2, le=101)


class OpticalScan2D(StrictInput):
    system: OpticalSystem
    x: ScanAxis
    y: ScanAxis


def scan_system_2d(config):
    scan = config if isinstance(config, OpticalScan2D) else OpticalScan2D.model_validate(config)
    if scan.system.mode == "single_pass":
        raise ValueError("Stability map requires a resonator")
    if (scan.x.element_index, scan.x.parameter) == (scan.y.element_index, scan.y.parameter):
        raise ValueError("Two axes must change different parameters")
    for axis in (scan.x, scan.y):
        if axis.element_index >= len(scan.system.elements) or axis.stop <= axis.start:
            raise ValueError("Invalid scan range or element index")
        if axis.parameter not in SCAN_PARAMETERS[scan.system.elements[axis.element_index].kind]:
            raise ValueError("Scan parameter does not affect this element")
    xs, ys = np.linspace(scan.x.start, scan.x.stop, scan.x.count), np.linspace(scan.y.start, scan.y.stop, scan.y.count)
    maps = {"tangential": [], "sagittal": [], "stable_both": []}
    invalid = 0
    for y in ys:
        row = {key: [] for key in maps}
        for x in xs:
            raw = scan.system.model_dump()
            for axis, value in ((scan.x, x), (scan.y, y)):
                raw["elements"][axis.element_index][axis.parameter] = float(value)
            try:
                output = analyze_system(raw, profile=False)
                for plane in ("tangential", "sagittal"):
                    row[plane].append(output["planes"][plane]["m"])
                row["stable_both"].append(int(output["stable_both_planes"]))
            except ValueError:
                invalid += 1
                for key in row:
                    row[key].append(None)
        for key in maps:
            maps[key].append(row[key])
    return {"status": "completed", "x": xs.tolist(), "y": ys.tolist(), "x_axis": scan.x.model_dump(), "y_axis": scan.y.model_dump(),
            "maps": maps, "invalid_count": invalid, "grid_points": len(xs)*len(ys),
            "scope": "Sampled two-parameter map; null cells invalid. Stability does not establish output power or global optimum."}


def _matrix(element, plane):
    if element.kind == "space":
        return B.slab(element.length_mm, element.n)
    if element.kind == "lens":
        return B.thin_lens(element.focal_mm)
    if element.kind == "matrix":
        return np.array(element.matrix_s if plane == "sagittal" and element.matrix_s is not None else element.matrix_t).reshape(2, 2)
    if element.kind == "grin":
        g, n, length = element.gradient_per_mm, element.n, element.length_mm
        if not g:
            return B.slab(length, n)
        c, s = math.cos(g * length), math.sin(g * length)
        return np.array([[c, s / (n*g)], [-n*g*s, c]])
    if element.kind == "thick_lens":
        first = np.eye(2) if element.front_radius_mm is None else B.thin_lens(element.front_radius_mm / (element.n-1)) if element.n != 1 else np.eye(2)
        last = np.eye(2) if element.back_radius_mm is None else B.thin_lens(-element.back_radius_mm / (element.n-1)) if element.n != 1 else np.eye(2)
        return last @ B.slab(element.length_mm, element.n) @ first
    return B.mirror_flat() if element.radius_mm is None else B.mirror_curved(element.radius_mm, element.aoi_deg, plane)


def _point(q, z, wl, n=1):
    # Reduced q has identical spot radius on either side of a flat interface.
    physical_q = n * q
    radius = B.radius_from_q(physical_q)
    return {"z_mm": float(z), "radius_mm": B.w_from_q(physical_q, wl, n),
            "curvature_mm": float(radius) if math.isfinite(radius) else None,
            "q_real_mm": float(physical_q.real), "q_imag_mm": float(physical_q.imag), "n": n}


def analyze_system(config: OpticalSystem | dict, *, profile=True) -> dict:
    system = config if isinstance(config, OpticalSystem) else OpticalSystem.model_validate(config)
    paths = system.elements
    if system.mode == "standing_wave":
        outward = paths[1:]
    else:
        outward = paths
    effective_wl = system.wavelength_nm * system.beam_quality_m2
    result = {"status": "completed", "engine": "LaserClaw Python/NumPy ABCD (not the Rezonator C++ runtime)",
              "mode": system.mode, "wavelength_nm": system.wavelength_nm, "effective_wavelength_nm": effective_wl, "system": system.model_dump(),
              "scope": ["Paraxial, coplanar tangential/sagittal axes; M²=1 eigenmodes, equivalent M² single-pass", "Flat media, thin/thick lenses at normal incidence, focusing GRIN and real reduced ABCD elements; ideal alignment",
                        "No gain, output-power, diffraction/aperture, or thermal-field prediction"], "planes": {}}
    for plane in ("tangential", "sagittal"):
        matrices = [_matrix(e, plane) for e in outward]
        if system.mode == "standing_wave":
            for e in reversed(paths[1:-1]):
                a, b, c, d = _matrix(e, plane).ravel()
                matrices.append(np.array([[d, b], [c, a]]))
            matrices.append(_matrix(paths[0], plane))
        matrix = B.system_matrix(matrices)
        info = {"matrix": matrix.tolist()}
        if system.mode == "single_pass":
            q = B.q_from_beam(system.input_radius_mm, system.input_curvature_mm, effective_wl)
        else:
            info.update(B.stability(matrix))
            q = B.cavity_mode_q(matrix) if info["stable"] else None
        if q is None:
            info.update({"samples": [], "elements": [], "message": "No confined Gaussian eigenmode (unstable or marginal)."})
            result["planes"][plane] = info
            continue
        info["input"] = _point(q, 0, effective_wl)
        z, samples, nodes, waists = 0., [], [], []
        if system.mode == "standing_wave":
            nodes.append({"name": paths[0].name, "kind": "mirror", **_point(q, 0, system.wavelength_nm)})
        for element in outward:
            if profile and element.kind == "thick_lens":
                first = np.eye(2) if element.front_radius_mm is None or element.n == 1 else B.thin_lens(element.front_radius_mm / (element.n-1))
                inside = B.propagate_q(first, q)
                distances = set(np.linspace(0, element.length_mm, system.samples_per_segment))
                focus = -inside.real * element.n
                if 0 <= focus <= element.length_mm:
                    distances.add(focus)
                    waists.append({"z_mm": z+focus, "radius_mm": B.w_from_q(complex(0, inside.imag*element.n), effective_wl, element.n), "rayleigh_length_mm": inside.imag*element.n, "segment": element.name})
                samples.extend(_point(inside+d/element.n, z+d, effective_wl, element.n) for d in sorted(distances))
            if profile and element.kind == "grin":
                for distance in np.linspace(0, element.length_mm, system.samples_per_segment):
                    sub = element.model_copy(update={"length_mm": float(distance)})
                    samples.append(_point(B.propagate_q(_matrix(sub, plane), q), z+distance, effective_wl, element.n))
            if profile and element.kind == "space":
                distances = set(np.linspace(0, element.length_mm, system.samples_per_segment))
                waist_at = -q.real * element.n
                if 0 <= waist_at <= element.length_mm:
                    zr = q.imag * element.n
                    waists.append({"z_mm": z + waist_at, "radius_mm": B.w_from_q(complex(0, zr), effective_wl, element.n),
                                   "rayleigh_length_mm": zr, "segment": element.name})
                    distances.add(waist_at)
                    for multiplier in (-5, -2, -1, -.5, -.25, .25, .5, 1, 2, 5):
                        distance = waist_at + multiplier * zr
                        if 0 < distance < element.length_mm:
                            distances.add(distance)
                for distance in sorted(distances):
                    samples.append(_point(q + distance / element.n, z + distance, effective_wl, element.n))
            q = B.propagate_q(_matrix(element, plane), q)
            z += element.length_mm
            nodes.append({"name": element.name, "kind": element.kind, **_point(q, z, effective_wl)})
        info.update({"output": _point(q, z, effective_wl), "samples": samples, "elements": nodes, "waists": waists})
        if system.mode == "single_pass":
            w0, distance = B.waist_from_q(q, effective_wl)
            info["downstream_waist_in_air"] = {"radius_mm": w0, "distance_from_output_mm": distance,
                                               "note": "Free propagation beyond last element; negative distance is a virtual upstream waist."}
        result["planes"][plane] = info
    if system.mode != "single_pass":
        result["stable_both_planes"] = all(p["stable"] for p in result["planes"].values())
    return result


def scan_system(config: OpticalScan | dict) -> dict:
    scan = config if isinstance(config, OpticalScan) else OpticalScan.model_validate(config)
    if scan.element_index >= len(scan.system.elements) or scan.stop <= scan.start:
        raise ValueError("Scan requires an existing element index and stop > start")
    element = scan.system.elements[scan.element_index]
    permitted = SCAN_PARAMETERS
    if scan.parameter not in permitted[element.kind]:
        raise ValueError("Scan parameter does not affect the chosen element type")
    rows = []
    for value in np.linspace(scan.start, scan.stop, scan.count):
        raw = scan.system.model_dump()
        raw["elements"][scan.element_index][scan.parameter] = float(value)
        try:
            solved = analyze_system(raw, profile=False)
            row = {"value": float(value), "status": "completed", "stable_both_planes": solved.get("stable_both_planes")}
            for plane, data in solved["planes"].items():
                row[plane] = {key: data[key] for key in ("m", "stable", "input", "output", "downstream_waist_in_air") if key in data}
            rows.append(row)
        except ValueError as exc:
            rows.append({"value": float(value), "status": "invalid", "message": str(exc)})
    intervals = {}
    for plane in ("tangential", "sagittal", "both"):
        spans, active = [], None
        for row in rows:
            stable = row.get("stable_both_planes") if plane == "both" else row.get(plane, {}).get("stable")
            if stable:
                if active is None:
                    active = {"first_stable_sample": row["value"], "last_stable_sample": row["value"]}
                    spans.append(active)
                active["last_stable_sample"] = row["value"]
            else:
                active = None
        intervals[plane] = spans
    return {"status": "completed", "mode": scan.system.mode, "parameter": scan.parameter, "element": element.name, "points": rows,
            "stable_intervals_sampled": intervals, "step": (scan.stop - scan.start) / (scan.count - 1),
            "scope": "Finite one-parameter grid; no global optimum claim. Recalculate chosen candidate with analyze_optical_system.",
            "valid_count": sum(row["status"] == "completed" for row in rows),
            "stable_count": sum(row.get("stable_both_planes") is True for row in rows) if scan.system.mode != "single_pass" else None}
