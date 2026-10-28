"""Evidence-backed requirements. Proposed geometry never becomes a user fact."""
from __future__ import annotations

import math
import re
from typing import Any

FIELDS = {
    "pump_wavelength_nm": ("泵浦波长", "nm"), "laser_wavelength_nm": ("激光波长", "nm"),
    "pump_power_w": ("泵浦最大功率", "W"), "pump_source": ("泵浦出光方式", ""),
    "gain_material": ("增益材料", ""), "cavity_type": ("腔型", ""),
    "crystal_width_mm": ("晶体宽度", "mm"), "crystal_height_mm": ("晶体高度", "mm"),
    "crystal_length_mm": ("晶体总长", "mm"), "active_length_mm": ("掺杂段长度", "mm"),
    "front_cap_mm": ("前端帽长度", "mm"), "rear_cap_mm": ("后端帽长度", "mm"),
    "doping_pct": ("掺杂标称值", "%"), "cut_axis": ("晶体切向", ""),
    "ar_wavelengths_nm": ("标签双面 AR 波长", "nm"), "crystal_part": ("晶体型号 / 编号", ""),
    "collimator_owned": ("已有准直镜", ""), "focus_lens_owned": ("已有聚焦镜", ""),
    "collimator_roc_mm": ("准直平凸镜曲率半径", "mm"),
    "collimator_f_mm": ("准直镜焦距", "mm"), "focus_f_mm": ("聚焦镜焦距", "mm"),
    "collimator_index": ("准直镜材料折射率（泵浦波长）", ""),
    "fiber_core_um": ("光纤芯径", "μm"), "fiber_na": ("光纤 NA", ""),
    "target_mode_radius_um": ("目标腔模半径", "μm"),
    "crystal_index": ("晶体激光波长折射率", ""), "pump_index": ("晶体泵浦波长折射率", ""),
    "crystal_front_mm": ("M1 到晶体前表面", "mm"), "max_cavity_mm": ("最大腔长", "mm"),
    "oc_transmission_pct": ("输出镜透过率", "%"), "candidate_rank": ("采用候选序号", ""),
    "terminal_offset_mm": ("M2 到测量终端距离", "mm"),
    "input_mirror_near_crystal": ("输入镜靠近晶体", ""),
    "output_roc_mm": ("固定输出镜曲率半径", "mm"),
    "input_roc_mm": ("固定输入镜曲率半径", "mm"),
    "input_mirror_flat": ("输入镜为平面", ""),
    "output_mirror_flat": ("输出镜为平面", ""),
    "input_mirror_owned": ("已有输入镜", ""),
    "output_mirror_owned": ("已有输出镜", ""),
    "mirror_coatings_user_confirmed": ("用户确认腔镜镀膜用途匹配", ""),
    "output_gap_mm": ("固定晶体后端面到 M2", "mm"),
    "min_output_gap_mm": ("M2 最小装配间隙", "mm"),
    "max_output_gap_mm": ("M2 最大搜索间隙", "mm"),
    "pump_focus_depth_mm": ("泵浦焦点距晶体前端面", "mm"),
    "source_z_mm": ("固定光纤端位置，相对 M1", "mm"),
    "collimator_z_mm": ("固定准直镜主面位置，相对 M1", "mm"),
    "focus_lens_z_mm": ("固定聚焦镜主面位置，相对 M1", "mm"),
    "collimator_inventory_id": ("指定准直镜库存 ID", ""),
    "focus_lens_inventory_id": ("指定聚焦镜库存 ID", ""),
    "M1_inventory_id": ("指定输入镜库存 ID", ""),
    "M2_inventory_id": ("指定输出镜库存 ID", ""),
    "crystal_inventory_id": ("指定晶体库存 ID", ""),
}
TEXT_FIELDS = {"pump_source", "gain_material", "cavity_type", "cut_axis", "crystal_part"}
BOOL_FIELDS = {"collimator_owned", "focus_lens_owned", "input_mirror_near_crystal", "input_mirror_flat", "output_mirror_flat", "input_mirror_owned", "output_mirror_owned", "mirror_coatings_user_confirmed"}


def extraction_prompt() -> str:
    return """You extract explicit laboratory requirements, NOT a design or recommendations.
Read the case TITLE, description, user's new message, inventory and attached labels. Existing facts are context only.
Return JSON {"facts":[{"key":KEY,"value":VALUE,"quote":"literal evidence",
"source":"message|title|description|image:<attachment_id>|inventory:<item_id>"}],"notes":["brief ambiguities in Chinese"]}.
Only emit facts explicitly stated in the input or visibly printed in the image.
Do not invent refractive indices, focal lengths, NA, fiber diameter, thermal lens, output power or mirror parameters.
R50 is a radius of curvature of 50 mm, NOT a focal length of 50 mm. FL100 is focal length 100 mm.
M1 is always the INPUT mirror, M2 always the OUTPUT mirror, regardless of curvature. A concave R200 INPUT and flat OUTPUT means input_roc_mm=200, input_mirror_flat=false, output_mirror_flat=true. Never swap these roles to fit an older template. When explicitly changing a mirror to flat, retract its previous roc with null. When mirrors are now owned, record ownership. A coating described as suitable or similar does NOT establish a numerical T/R or substrate data; emit mirror_coatings_user_confirmed only.
For composite crystals preserve front endcap, ACTIVE doped segment, rear endcap and TOTAL physical length separately.
Read 808 vs 880 literally. AR wavelength lists must match the label; never silently add the requested pump wavelength.
Use null only when the latest message explicitly retracts a previous fact. Do not output null for omitted fields.
Resolve follow-up statements using prior facts, and label each new fact with its current evidence.
The NEW message overrides old context. Do not re-emit an old title/description value over an existing fact.
The numerical planner supplies engineering assumptions and missing component proposals separately; do not invent them here.
If M1 should be close to the crystal, emit input_mirror_near_crystal=true; do not invent a numerical gap.
Distinguish output_gap_mm (crystal REAR face to M2) from crystal_front_mm (M1 to crystal FRONT face).
Fixed z coordinates are relative to M1 coating plane; preserve negative pump-side coordinates.
Extract inventory IDs only when explicitly selected/referenced. Read crystal details from a selected inventory record.
Do not turn an arbitrary unselected inventory item into an owned component. Unselected inventory is for the solver to search.
An SM9/125 fiber marking is nominal fiber geometry, not a measured 808 nm mode field or numerical aperture.
Normalize units: wavelengths nm, lengths/focal lengths mm, fiber core and mode radius micrometres, power W, percentages 0..100.
cavity_type: linear|ring|bow-tie|custom. pump_source: fiber|free_space|unknown. gain_material e.g. Nd:YVO4.
Boolean owned fields mean user explicitly has that component. input_mirror_near_crystal is also boolean. ar_wavelengths_nm is a numeric list.
crystal_part is an identifier string. All other non-text fields are numbers. Return only these keys:
""" + "\n".join(f"{key}: {label} ({unit})" for key, (label, unit) in FIELDS.items())


def validate_fact(key: str, value: Any):
    if key not in FIELDS:
        raise ValueError("unsupported field")
    if value is None:
        return None
    if key in TEXT_FIELDS:
        if not isinstance(value, str) or len(value) > 300:
            raise ValueError("invalid text")
        return value.strip()
    if key in BOOL_FIELDS:
        if not isinstance(value, bool):
            raise ValueError("expected boolean")
        return value
    if key == "ar_wavelengths_nm":
        if not isinstance(value, list) or len(value) > 20 or any(v is None for v in value):
            raise ValueError("invalid wavelength list")
        return [validate_fact("laser_wavelength_nm", v) for v in value]
    if isinstance(value, bool):
        raise ValueError("expected number")
    number = float(value)
    if key in {"source_z_mm", "collimator_z_mm", "focus_lens_z_mm"}:
        if not math.isfinite(number) or not -10000 <= number < 0:
            raise ValueError("pump-side coordinates must be negative, relative to M1")
        return number
    if not math.isfinite(number) or number < 0 or number > 100000:
        raise ValueError("number out of range")
    if key in {"front_cap_mm", "rear_cap_mm", "crystal_front_mm"}:
        return number
    if number == 0:
        raise ValueError("must be positive")
    if key.endswith("_index") and not 1 < number < 5:
        raise ValueError("invalid refractive index")
    if key == "fiber_na" and number > 1:
        raise ValueError("NA must be <= 1")
    if key.endswith("_pct") and number >= 100:
        raise ValueError("percentage must be < 100")
    if key == "candidate_rank" and (number != int(number) or number > 5):
        raise ValueError("candidate must be 1..5")
    if key.endswith("_inventory_id") and number != int(number):
        raise ValueError("inventory ID must be an integer")
    return number


def merge_facts(previous: dict, extracted: dict, sources: dict[str, str], image_ids: list[int]):
    facts = dict(previous or {})
    changes, notes = [], list(extracted.get("notes") or [])[:10]
    for item in extracted.get("facts", []):
        if not isinstance(item, dict):
            continue
        key, source, quote = item.get("key"), item.get("source"), str(item.get("quote") or "").strip()
        image_source = source in {f"image:{aid}" for aid in image_ids}
        # Text quotes must be present, not hallucinated references to old answers.
        def normalize(s):
            return re.sub(r"\s+", "", s).casefold()
        if not quote or (not image_source and (source not in sources or normalize(quote) not in normalize(sources[source]))):
            notes.append(f"未采纳无可核对出处的字段：{key}")
            continue
        try:
            value = validate_fact(key, item.get("value"))
        except (ValueError, TypeError):
            notes.append(f"未采纳格式或范围不合法的字段：{key}")
            continue
        if key == "collimator_f_mm" and re.search(r"\bR\s*\d", quote, re.I) and not re.search(r"焦距|focal|\bFL?\s*[=:]?\s*\d", quote, re.I):
            notes.append("R 标识只能支持曲率半径，未采纳由 R 直接推定的准直焦距。")
            continue
        old = facts.get(key)
        if old and old.get("value") != value:
            changes.append({"key": key, "before": old.get("value"), "after": value, "quote": quote})
        if value is None:
            facts.pop(key, None)
        else:
            facts[key] = {"value": value, "quote": quote, "source": source,
                          "label": FIELDS[key][0], "unit": FIELDS[key][1],
                          "verification": "image_reading" if image_source else "user_stated"}
    return facts, changes, notes


def mock_extract(context: dict) -> dict:
    """Small explicit-text parser for demo/offline mode. Never pretends to read images."""
    facts = []
    for source in ("title", "description", "message"):
        text = context.get(source, "")
        patterns = {
            "pump_wavelength_nm": r"(\d+(?:\.\d+)?)\s*(?:纳米|nm)\s*(?:泵浦|pump)",
            "laser_wavelength_nm": r"(\d+(?:\.\d+)?)\s*(?:纳米|nm)\s*(?:激光|laser)",
            "pump_power_w": r"(?:最高|最大功率|功率|power)\s*[:：=]?\s*(\d+(?:\.\d+)?)\s*[wW瓦]",
            "collimator_roc_mm": r"\bR\s*(\d+(?:\.\d+)?)",
            "focus_f_mm": r"\bFL\s*(\d+(?:\.\d+)?)",
            "collimator_f_mm": r"准直(?:镜|透镜)?(?:焦距)?\s*[:：=]?\s*(\d+(?:\.\d+)?)\s*mm",
            "fiber_core_um": r"芯径\s*[:：=]?\s*(\d+(?:\.\d+)?)\s*(?:um|μm|微米)",
            "fiber_na": r"\bNA\s*[:：=]?\s*(\d+(?:\.\d+)?)",
            "candidate_rank": r"(?:采用|选择)(?:候选)?(?:方案)?\s*(\d)",
            "output_gap_mm": r"(?:M2距晶体后端面|输出镜距晶体后端面)\s*[:：=]?\s*(\d+(?:\.\d+)?)\s*mm",
            "output_roc_mm": r"M2\s*(?:曲率)?\s*R\s*=?\s*(\d+(?:\.\d+)?)",
        }
        for key, pattern in patterns.items():
            if match := re.search(pattern, text, re.I):
                facts.append({"key": key, "value": float(match[1]), "source": source, "quote": match[0]})
        for token, key, value in [("直线腔", "cavity_type", "linear"), ("光纤", "pump_source", "fiber"),
                                   ("掺钕钒酸钇", "gain_material", "Nd:YVO4"), ("Nd:YVO4", "gain_material", "Nd:YVO4")]:
            if token in text:
                facts.append({"key": key, "value": value, "source": source, "quote": token})
        if match := re.search(r"(?:输入镜|后腔镜|M1).{0,15}(?:紧贴|靠近|贴近)晶体", text, re.I):
            facts.append({"key": "input_mirror_near_crystal", "value": True, "source": source, "quote": match[0]})
    return {"facts": facts, "notes": ["演示模式仅做有限文本提取，不读取图片；真实物理计算仍可执行。"]}
