"""Deterministic Rezonator 2 schema export, based on the bundled .rez examples.

Exports the cold resonator only: a standing wave traverses the crystal twice.
Pump wavelength and output T are not eigenmode matrix parameters.
"""


def cold_cavity_schema(candidate, wavelength_nm):
    crystal = candidate["crystal"]
    front, total = crystal["position_mm"], crystal["thickness_mm"]

    def element(kind, label, title, params):
        return {"type": kind, "label": label, "title": title, "is_disabled": False,
                "params": {key: {"value": value, "unit": unit} for key, (value, unit) in params.items()}}

    def mirror(label, radius):
        return element("ElemFlatMirror", label, f"{label} coating plane", {}) if radius is None else element("ElemCurveMirror", label, f"{label} concave toward cavity", {"R": (radius, "mm"), "Alpha": (0, "deg")})

    elements = [mirror("M1", candidate.get("R1_mm"))]
    if front > 0:
        elements.append(element("ElemEmptyRange", "d1", "M1 to crystal FRONT face", {"L": (front, "mm")}))
    elements.append(element("ElemPlate", "G", "Full crystal including undoped endcaps", {
        "L": (total, "mm"), "n": (crystal["n"], "none")}))
    elements.append(element("ElemEmptyRange", "d2", "Crystal REAR face to M2", {
        "L": (candidate["length_mm"] - front - total, "mm")}))
    elements.append(mirror("M2", candidate["R2_mm"]))
    return {"schema_version": "2.0", "trip_type": "SW", "builtin_params": {"lambda": {"value": wavelength_nm, "unit": "nm"}},
            "custom_params": {}, "elements": elements, "formulas": [], "param_links": [], "pumps": [], "windows": []}
