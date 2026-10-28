"""Deterministic end-pumped linear-cavity design, with explicit model boundaries.

Coordinates are physical mm, M1 coating plane z=0; all beam widths are radii.
The Nd:YVO4 index uses the manufacturer's published Sellmeier relation.
"""
from __future__ import annotations

import math
from typing import Any

from ..physics import beam as B
from ..physics.design import _round_trip_with_lens
from ..physics.toolkit import _FLAT_ROC_MM, _analyze_length, beam_envelope
from .planning import BK7_SOURCE, resolve_inputs

INDEX_SOURCE = "https://www.crystech.com/Laser_Crystal/446.html"
CATALOGUE_ROCS = [50, 75, 100, 150, 200, 250, 300, 400, 500, 750, 1000]


def yvo4_index(wavelength_nm: float, polarization: str = "e") -> float:
    lam2 = (wavelength_nm / 1000) ** 2
    if not 400 <= wavelength_nm <= 2000:
        raise ValueError("YVO4 折射率模型仅在 400–2000 nm 内使用")
    n2 = (4.59905 + 0.110534 / (lam2 - 0.04813) - 0.012676 * lam2) if polarization == "e" else (
        3.77834 + 0.069736 / (lam2 - 0.04724) - 0.010813 * lam2)
    return math.sqrt(n2)


def mirror_radius(value):
    return _FLAT_ROC_MM if value is None else value


def mirror_label(value):
    return "平面" if value is None else f"凹面 R={value:g} mm"


def _radius_at(z: float, length: float, roc: float | None, wl: float, crystal: dict, f: float | None = None, r1=None) -> float:
    q = B.cavity_mode_q(_round_trip_with_lens(length, mirror_radius(r1), mirror_radius(roc), crystal, f))
    if q is None:
        raise ValueError("unstable cavity")
    front, n = crystal["position_mm"], crystal["n"]
    q = B.propagate_q(B.free_space(front), q)
    q = B.propagate_q(B.interface_flat(1, n), q)
    dz = z - front
    half = crystal["thickness_mm"] / 2
    if f and dz > half:
        q = B.propagate_q(B.free_space(half), q)
        q = B.propagate_q(B.thin_lens(f), q)
        q = B.propagate_q(B.free_space(dz - half), q)
    else:
        q = B.propagate_q(B.free_space(dz), q)
    return B.w_from_q(q, wl, n)


def distance_scan(candidate: dict, wl: float, max_length: float, min_gap: float) -> dict:
    """Move M2, holding M1, crystal and mirror ROC fixed. Distances are physical."""
    crystal = candidate["crystal"]
    front, total, n = crystal["position_mm"], crystal["thickness_mm"], crystal["n"]
    roc, r1 = candidate["R2_mm"], candidate.get("R1_mm")
    curved = min(mirror_radius(roc), mirror_radius(r1))
    current_gap = candidate["length_mm"] - front - total
    max_gap = max(current_gap, min(max_length - front - total, curved - front - total / n + 20))
    gaps = sorted(set([round(current_gap, 6)] + [float(i) for i in range(math.ceil(min_gap), math.floor(max_gap) + 1)]))
    rows = []
    for gap in gaps:
        length = front + total + gap
        scenarios = []
        for f in [None, 500, 200, 100, 50]:
            matrix = _round_trip_with_lens(length, mirror_radius(r1), mirror_radius(roc), crystal, f)
            state = B.stability(matrix)
            scenarios.append({"f_mm": f, "stable": state["stable"], "m": round(state["m"], 6)})
        stable = scenarios[0]["stable"]
        rows.append({"gap_mm": gap, "length_mm": round(length, 6), "stable": stable, "m": scenarios[0]["m"],
                     "mode_radius_um": round(_radius_at(candidate["active_center_mm"], length, roc, wl, crystal, r1=r1) * 1000, 3) if stable else None,
                     "thermal": scenarios})
    return {"rows": rows, "selected_gap_mm": current_gap, "cold_upper_exclusive_mm": max(0, curved - front - total / n) if r1 is None or roc is None else None,
            "formula": "0 < g1·g2 < 1，gi=1−Leff/Ri；平面镜 gi=1。Leff=d1+晶体总长/n+d2。",
            "note": "冷腔稳定边界是解析值；热透镜为离散场景，稳定不等于功率最优。", "step_mm": 1}


def _thermal_stability_m(length, roc, crystal, focal, r1=None):
    """Trace of the same round trip, in reduced ray coordinates (y, n*y')."""
    if r1 is not None:
        return B.stability(_round_trip_with_lens(length, mirror_radius(r1), mirror_radius(roc), crystal, focal))["m"]
    roc = mirror_radius(roc)
    a = crystal["position_mm"] + crystal["thickness_mm"] / (2 * crystal["n"])
    b = length - crystal["position_mm"] - crystal["thickness_mm"] + crystal["thickness_mm"] / (2 * crystal["n"])
    k = 0 if focal is None else crystal["n"] / focal
    d, e, c = 1 - 2 * b / roc, 2 * b * (1 - b / roc), -2 / roc
    return d + a * c - k * (e + 2 * a * d) + a * e * k * k


def _band(item: dict, wl: float, kind: str) -> bool:
    return any(b["wl_min_nm"] <= wl <= b["wl_max_nm"] and b["function"] in (
        {"AR", "HT"} if kind == "HT" else {kind}) for b in item.get("coatings", []))


def match_mirrors(inventory: list[dict], *, role: str, roc: float | None, wl: float, pump: float,
                  min_diameter: float, transmission: float | None = None) -> dict:
    matched, partial, rejected = [], [], []
    for item in inventory:
        if item["category"] != "mirror":
            continue
        reasons, unknowns = [], []
        if item["condition"] == "damaged":
            reasons.append("已标损坏")
        elif item["condition"] != "ok":
            unknowns.append("状态待复核")
        if item["available_quantity"] < 1:
            reasons.append("无可用库存（含借出）")
        if roc is None:
            if not item.get("roc_is_flat"):
                (reasons if item.get("roc_mm") else unknowns).append("需平面镜")
        elif item.get("roc_is_flat"):
            reasons.append("平面镜与所需凹面镜不符")
        elif item.get("roc_mm") is None:
            unknowns.append("曲率未知")
        elif abs(item["roc_mm"] - roc) > 0.01 * roc:
            reasons.append("曲率不符")
        if item.get("diameter_mm") is None:
            unknowns.append("口径未知")
        elif item["diameter_mm"] < min_diameter:
            reasons.append("口径不足")
        if role == "M1":
            for wave, kind in [(wl, "HR"), (pump, "HT")]:
                if not _band(item, wave, kind):
                    unknowns.append(f"未标明 {kind}@{wave:g} nm")
        else:
            bands = [b for b in item.get("coatings", []) if b["wl_min_nm"] <= wl <= b["wl_max_nm"]
                     and b["function"] == "PR"]
            if not bands:
                unknowns.append(f"未标明部分透过 @{wl:g} nm")
            else:
                values = [b["value_pct"] if b.get("value_type") == "T" else 100 - b["value_pct"]
                          for b in bands if b.get("value_pct") is not None and b.get("comparator") == "="
                          and b.get("value_type") in {"T", "R"}]
                if not values:
                    unknowns.append("输出耦合率需要实测；R 换算 T 还需扣除吸收/散射")
                elif transmission is not None and not any(abs(v - transmission) <= 0.25 for v in values):
                    reasons.append("标称输出耦合率不符")
                if any(b.get("value_type") == "R" for b in bands):
                    unknowns.append("反射率不能单独证明透过率，需透射测量")
        if item.get("parse_confidence") == "needs_review":
            unknowns.append("原始规格需复核")
        entry = {"id": item["id"], "name": item["name"], "location": item.get("location"),
                 "available_quantity": item["available_quantity"], "raw_spec": item.get("raw_spec"),
                 "reasons": reasons, "unknowns": unknowns}
        if reasons:
            rejected.append(entry)
        elif unknowns:
            partial.append(entry)
        else:
            matched.append(entry)
    return {"matched": matched[:5], "needs_verification": partial[:5], "rejected": rejected[:5],
            "counts": {"matched": len(matched), "needs_verification": len(partial), "rejected": len(rejected)},
            "status": "in_stock" if matched else "verify_or_buy" if partial else "purchase"}


def _pump_layout(values: dict, front: float, active_center: float, total: float, n: float) -> dict:
    f1, f2 = values.get("collimator_f_mm"), values.get("focus_f_mm")
    notes = []
    if values.get("input_roc_mm"):
        notes.append("凹面输入镜对 808 nm 的透射具有折射光焦度；基底材料、厚度和背面曲率未知。以下泵浦坐标为忽略输入镜透射光焦度的基线，不能作为最终聚焦镜安装距离；请测透过 M1 后的焦散或补入两面参数。")
    if not f1 and values.get("collimator_roc_mm") and values.get("collimator_index"):
        f1 = values["collimator_roc_mm"] / (values["collimator_index"] - 1)
        notes.append("准直镜按空气中薄平凸透镜 f=R/(n−1) 计算；厚透镜主面位置尚未计入。")
    missing = [key for key, val in [("collimator_f_mm", f1), ("focus_f_mm", f2)] if not val]
    if values.get("pump_source") != "fiber":
        missing.append("pump_source")
    if missing:
        return {"status": "needs_specs", "missing": missing, "points": [], "positions": {},
                "notes": notes, "formula": "光纤→准直镜=f1；两镜间距=f1+f2；像面芯径≈芯径×f2/f1。"}
    depth = values.get("pump_focus_depth_mm", active_center - front)
    air_after_focus = f2 - depth / n
    focus_z = front - air_after_focus
    if focus_z >= -2:
        return {"status": "no_fit", "missing": [], "points": [], "positions": {},
                "notes": ["现有聚焦镜焦距与当前晶体位置不相容：聚焦镜会落在 M1 之后或间隙不足。"]}
    col_z = values.get("collimator_z_mm", values["source_z_mm"] + f1 if "source_z_mm" in values else focus_z - f1 - f2)
    fiber_z = values.get("source_z_mm", col_z - f1)
    positions = {"source": fiber_z, "collimator": col_z, "focus_lens": focus_z}
    conflicts = []
    if not math.isclose(col_z - fiber_z, f1, abs_tol=.05):
        conflicts.append("固定光纤端到准直镜的间距不等于准直焦距，无法满足当前准直条件。")
    if focus_z - col_z < 5:
        conflicts.append("固定准直镜在聚焦镜之后或镜间装配距离不足 5 mm。")
    if "focus_lens_z_mm" in values and not math.isclose(values["focus_lens_z_mm"], focus_z, abs_tol=.05):
        conflicts.append("固定聚焦镜位置、晶体位置和指定焦点深度不能同时满足。")
    if conflicts:
        return {"status": "no_fit", "missing": [], "points": [], "positions": {}, "notes": conflicts}
    beam_assumptions = []
    for key in ["fiber_core_um", "fiber_na"]:
        if not values.get(key):
            missing.append(key)
    core = values.get("fiber_core_um", 200)
    na = values.get("fiber_na", .12)
    if "fiber_core_um" in missing:
        beam_assumptions.append("纤芯未知，包络场景暂用 200 μm；位置计算不依赖该假设。")
    if "fiber_na" in missing:
        beam_assumptions.append("NA 未知，包络场景暂用 0.12；位置计算不依赖 NA，准直口径需按实测 NA 更新。")
    r = core / 2000
    # Filled-core/filled-NA second-moment surrogate, NOT a measured Gaussian.
    effective_wl = math.pi * r * na * 1e6
    if effective_wl < values["pump_wavelength_nm"]:
        return {"status": "geometry_only", "missing": missing, "points": [], "positions": positions,
                "notes": notes + ["所给纤芯半径×NA 小于高斯衍射极限，不能同时视作光束半径和远场角；仅给几何坐标。"],
                "focus_depth_mm": depth, "focus_z_mm": front + depth}
    q = complex(0, r / na)
    z = fiber_z
    points = [{"z_mm": z, "w_mm": r}]
    elements = [(col_z, 1, f1), (focus_z, 1, f2), (front, n, None),
                (front + total, 1, None)]
    current_n = 1.0
    for end, next_n, lens in elements:
        count = min(400, max(2, int((end - z) / 3)))
        dz = (end - z) / count
        for _ in range(count):
            q = B.propagate_q(B.free_space(dz), q)
            z += dz
            points.append({"z_mm": round(z, 5), "w_mm": round(B.w_from_q(q, effective_wl, current_n), 6)})
        if lens:
            q = B.propagate_q(B.thin_lens(lens), q)
        elif next_n != current_n:
            q = B.propagate_q(B.interface_flat(current_n, next_n), q)
            current_n = next_n
    return {"status": "assumed_beam" if missing else "geometric_model", "missing": missing, "points": points,
            "positions": positions, "focus_depth_mm": depth, "focus_z_mm": front + depth,
            "collimator_f_mm": f1, "focus_f_mm": f2,
            "image_radius_mm": r * f2 / f1, "collimated_radius_mm": f1 * na,
            "estimated_m2": math.pi * r * na / (values["pump_wavelength_nm"] * 1e-6),
            "beam_assumptions": beam_assumptions, "assumed_na": na if "fiber_na" in missing else None,
            "notes": notes + beam_assumptions + ["薄透镜共轭成像；默认镜间距 f1+f2，已有准直段位置允许改变镜间距；芯径与 NA 视为填满。",
                               "M1 透射基底的厚度/主面、透镜像差、偏振和装配公差尚需按实物校准。"]}


def solve_design(facts: dict, inventory: list[dict]) -> dict[str, Any]:
    v, assumptions, issues, bindings = resolve_inputs(facts, inventory)
    missing = []
    result = {"schema": "optical_design_v2", "status": "needs_input", "facts": facts,
              "assumptions": assumptions, "issues": issues, "questions": missing, "candidates": [],
              "resolved_inputs": v, "component_bindings": bindings,
              "engine": {"name": "LaserClaw ABCD", "implementation": "Python / NumPy 自洽腔模内核",
                         "rezonator": "按标准近轴公式独立实现；未调用 Rezonator C++ 可执行程序。导出 .rez 可独立复算冷腔。",
                         "scope": "端泵两镜直线腔（曲率与输入/输出角色独立）、平面端面晶体、薄透镜泵浦基线、集总热透镜场景"},
              "sources": [{"title": "CRYSTECH Nd:YVO4: Sellmeier 与偏振资料", "url": INDEX_SOURCE},
                          {"title": "SCHOTT N-BK7 色散数据（透镜材料假设）", "url": BK7_SOURCE}],
              "power_prediction": {"output_w": None, "reason": "未提供吸收率、实际耦合效率与腔内损耗，不能预测输出功率或断言起振。"}}

    def ask(key, question, why):
        missing.append({"key": key, "question": question, "why": why})

    if any(i["level"] == "blocking" for i in issues):
        return result

    for key, question in [("pump_wavelength_nm", "泵浦波长是多少？"), ("laser_wavelength_nm", "目标激光波长是多少？"),
                          ("gain_material", "增益晶体是什么材料？"), ("crystal_length_mm", "晶体总长是多少（复合晶体含端帽）？"),
                          ("active_length_mm", "实际掺杂段多长？"), ("cavity_type", "使用直线腔还是其他腔型？")]:
        if not v.get(key):
            ask(key, question, "用于建立有物理依据的腔模型。")
    if v.get("cavity_type") and v["cavity_type"] != "linear":
        issues.append({"level": "blocking", "text": "此设计求解器支持端泵直线腔；环形/折叠腔不能套用当前几何。"})
        return result
    if missing:
        return result
    wl, pump = v["laser_wavelength_nm"], v["pump_wavelength_nm"]
    total, active = v["crystal_length_mm"], v["active_length_mm"]
    front_cap, rear_cap = v.get("front_cap_mm", 0), v.get("rear_cap_mm", 0)
    if not math.isclose(front_cap + active + rear_cap, total, abs_tol=0.01):
        issues.append({"level": "blocking", "text": "晶体端帽与掺杂段长度之和不等于总长，请纠正标签读取或补充端帽尺寸。"})
        return result
    width, height = v.get("crystal_width_mm"), v.get("crystal_height_mm")
    if not width or not height:
        ask("crystal_width_mm", "晶体横截面宽×高是多少？", "缺少孔径就不能确认腔模是否截断。")
    n, np = v.get("crystal_index"), v.get("pump_index")
    if "yvo4" in v["gain_material"].lower().replace("₄", "4"):
        if not n:
            n = yvo4_index(wl)
            assumptions.append({"name": "晶体折射率", "value": round(n, 6), "basis": "厂家 Sellmeier，假定 a-cut、π 偏振；低掺杂段与端帽使用相同折射率。", "source": INDEX_SOURCE})
        if not np:
            np = yvo4_index(pump)
            assumptions.append({"name": "泵浦折射率", "value": round(np, 6), "basis": "暂按 e 光支路；泵浦偏振待核对。", "source": INDEX_SOURCE})
    if not n or not np:
        ask("crystal_index", "请提供晶体在激光与泵浦波长的折射率。", "当前材料没有内置且已核对的色散模型。")
        return result
    coating = v.get("ar_wavelengths_nm", [])
    if pump not in coating:
        issues.append({"level": "verify", "text": f"晶体标签未确认 AR@{pump:g} nm（已读到：{coating or '无'}）。需厂家曲线或透射测量；不能把其他波长 AR 当作泵浦波长 AR。"})
    if wl not in coating:
        issues.append({"level": "verify", "text": f"晶体端面 AR@{wl:g} nm 尚未确认。"})
    max_l = v.get("max_cavity_mm", 300)
    if not 40 <= max_l <= 1000 or total > max_l - 5:
        issues.append({"level": "blocking", "text": "腔长搜索范围不合理：最大腔长需在 40–1000 mm 内，并容纳完整晶体及空气间隙。"})
        return result
    front_positions = [v["crystal_front_mm"]] if "crystal_front_mm" in v else [3, 5, 10, 20]
    depth = v.get("pump_focus_depth_mm", front_cap + active / 2)
    if not front_cap <= depth <= total - rear_cap:
        issues.append({"level": "blocking", "text": f"泵浦焦点深度 {depth:g} mm 不在掺杂段 {front_cap:g}–{total-rear_cap:g} mm 内；不能把无掺杂端帽当作增益段。"})
        return result
    assumptions.append({"name": "泵浦焦点", "value": depth, "unit": "mm（自晶体前端面）", "basis": "用户指定" if "pump_focus_depth_mm" in v else "先以掺杂段中心作为共轭像面；没有吸收分布时，这不是最高效率焦点位置。"})
    if "focus_lens_z_mm" in v:
        required_front = v["focus_lens_z_mm"] + v["focus_f_mm"] - depth / np
        if required_front < 0 or ("crystal_front_mm" in v and not math.isclose(v["crystal_front_mm"], required_front, abs_tol=.05)):
            issues.append({"level": "blocking", "text": "固定聚焦镜位置与 M1—晶体间距/焦点深度冲突；请解除一个位置约束。"})
            return result
        front_positions = [required_front]
    r1 = v.get("input_roc_mm")
    rocs = sorted(set(CATALOGUE_ROCS + [item["roc_mm"] for item in inventory if item["category"] == "mirror"
                                       and item.get("roc_mm") and 20 <= item["roc_mm"] <= 5000]))
    if v.get("output_roc_mm"):
        rocs = [v["output_roc_mm"]]
    if v.get("output_mirror_flat"):
        rocs = [None]
    stock_by_roc = {roc: bool(match_mirrors(inventory, role="M2", roc=roc, wl=wl, pump=pump,
                        min_diameter=6, transmission=v.get("oc_transmission_pct") if "oc_transmission_pct" in facts else None)["matched"]) for roc in rocs}
    assumed_target = v.get("target_mode_radius_um", 150) / 1000
    f1 = v.get("collimator_f_mm") or (v.get("collimator_roc_mm", 0) / (v["collimator_index"] - 1) if v.get("collimator_index") else None)
    if not v.get("target_mode_radius_um") and f1 and v.get("focus_f_mm") and v.get("fiber_core_um") and v.get("fiber_na") and facts.get("fiber_core_um", {}).get("verification") != "image_reading":
        assumed_target = v["fiber_core_um"] / 2000 * v["focus_f_mm"] / f1
        target_basis = "按已知纤芯与双透镜成像倍率估计泵浦像半径，作为模式匹配目标。"
    else:
        target_basis = "用户指定目标" if v.get("target_mode_radius_um") else "泵浦像尺寸未知，先以 150 μm 为探索目标；这不是实验事实或最优值。"
    assumptions.extend([
        {"name": "腔结构", "value": f"M1 {mirror_label(r1)} / M2 {'平面' if rocs == [None] else '曲率见候选'}", "basis": "M1 始终为泵浦输入镜，M2 始终为输出镜；保留用户已有面形和曲率，仅扫描未锁定参数。"},
        {"name": "目标晶体内模半径", "value": assumed_target * 1000, "unit": "μm", "basis": target_basis},
        {"name": "机械坐标", "value": "M1 镀膜面 z=0", "basis": "距离以 mm 计；外部透镜使用薄透镜主面，零件厚度与镜架间隙需复核。"},
    ])
    evaluated, stable = 0, 0
    shortlist = []
    rejected_layouts = []
    gap_min, gap_max = v["min_output_gap_mm"], v.get("max_output_gap_mm", max_l)
    if gap_max < gap_min or ("output_gap_mm" in v and v["output_gap_mm"] < gap_min):
        issues.append({"level": "blocking", "text": "固定 M2 距离或最大搜索距离小于最小装配间隙；请修正位置约束。"})
        return result
    for front in front_positions:
        crystal = {"n": n, "thickness_mm": total, "position_mm": front}
        center = front + front_cap + active / 2
        pump_layout = _pump_layout(v, front, center, total, np)
        if pump_layout["status"] == "no_fit":
            rejected_layouts.extend(pump_layout["notes"])
            continue
        for roc in rocs:
            per_pair = []
            gaps = [v["output_gap_mm"]] if "output_gap_mm" in v else range(math.ceil(gap_min), math.floor(min(gap_max, max_l - front - total)) + 1)
            for gap in gaps:
                length = front + total + gap
                if length > max_l:
                    continue
                evaluated += 1
                analysis = _analyze_length(length, mirror_radius(r1), mirror_radius(roc), wl, crystal)
                if not analysis.get("stable"):
                    continue
                radius = _radius_at(center, length, roc, wl, crystal, r1=r1)
                # Geometric envelope at both end faces and active center, not only waist.
                crystal_max = max(_radius_at(front + dz, length, roc, wl, crystal, r1=r1) for dz in [0, front_cap, total - rear_cap, total])
                if width and height and 3 * crystal_max >= min(width, height) / 2:
                    continue
                stable += 1
                err = abs(math.log(radius / assumed_target))
                penalty = sum(abs(_thermal_stability_m(length, roc, crystal, focal, r1)) >= 1 for focal in [None, 2000, 1000, 500, 300, 200]) / 6
                score = err + 2 * penalty + length / 3000 - (.08 if stock_by_roc[roc] else 0)
                per_pair.append({"length_mm": float(length), "R1_mm": r1, "R2_mm": roc,
                                 "crystal": crystal, "active_center_mm": center, "mode_radius_mm": radius,
                                 "crystal_max_radius_mm": crystal_max, "m": analysis["stability_m"], "score": score,
                                 "score_terms": {"mode_size": err, "thermal_instability": 2 * penalty, "length": length / 3000, "stock": -.08 if stock_by_roc[roc] else 0}})
            per_pair.sort(key=lambda c: c["score"])
            shortlist.extend(per_pair[:3])
    shortlist.sort(key=lambda c: c["score"])
    shortlist = shortlist[:60]
    for candidate in shortlist:
        thermal = []
        for f in [None, 2000, 1000, 500, 300, 200, 150, 100, 75, 50]:
            matrix = _round_trip_with_lens(candidate["length_mm"], mirror_radius(r1), mirror_radius(candidate["R2_mm"]), candidate["crystal"], f)
            state = B.stability(matrix)
            thermal.append({"f_mm": f, "dioptre": 0 if f is None else 1000 / f, "stable": state["stable"],
                            "m": round(state["m"], 5), "mode_radius_mm": round(_radius_at(candidate["active_center_mm"], candidate["length_mm"], candidate["R2_mm"], wl, candidate["crystal"], f, r1), 6) if state["stable"] else None})
        candidate["thermal_scan"] = thermal
        candidate["inventory_preference"] = stock_by_roc[candidate["R2_mm"]]
    shortlist.sort(key=lambda c: c["score"])
    # Keep distinct radii, so alternatives are actual purchasing options.
    chosen, seen = [], set()
    for candidate in shortlist:
        identity = (candidate["R2_mm"], candidate["length_mm"], candidate["crystal"]["position_mm"]) if len(rocs) == 1 else candidate["R2_mm"]
        if identity not in seen:
            chosen.append(candidate)
            seen.add(identity)
        if len(chosen) == 5:
            break
    result["search"] = {"evaluated": evaluated, "stable": stable, "radii_mm": rocs, "step_mm": 1,
                         "max_length_mm": max_l, "crystal_positions_mm": front_positions,
                         "objective": "满足已固定元件/位置与晶体孔径；按目标模半径偏差、指定热透镜场景稳定性、可用库存和短腔偏好排序。给出搜索范围内的综合最优候选，不预测最大输出功率。",
                         "score_formula": "|ln(w/w目标)| + 2×不稳定场景比例 + L/3000 − 0.08×库存匹配；越低越好",
                         "hard_constraints": {k: v[k] for k in ["crystal_front_mm", "output_gap_mm", "input_roc_mm", "input_mirror_flat", "output_mirror_flat", "output_roc_mm", "focus_lens_z_mm", "collimator_z_mm", "source_z_mm"] if k in v}}
    if not chosen:
        issues.append({"level": "blocking", "text": "扫描范围内未找到满足全部约束的稳定腔。" + "；".join(dict.fromkeys(rejected_layouts))})
        return result
    for rank, candidate in enumerate(chosen, 1):
        candidate["rank"] = rank
        candidate["mode_radius_mm"] = round(candidate["mode_radius_mm"], 6)
        candidate["score"] = round(candidate["score"], 5)
        front = candidate["crystal"]["position_mm"]
        length = candidate["length_mm"]
        envelope = beam_envelope(length, mirror_radius(r1), mirror_radius(candidate["R2_mm"]), wl, candidate["crystal"])
        candidate["beam_envelope"] = envelope
        candidate["pump"] = _pump_layout(v, front, candidate["active_center_mm"], total, np)
        if r1 is not None:
            candidate["pump"]["baseline_only"] = True
            candidate["pump"]["status"] = "input_mirror_unknown"
        candidate["placement"] = {"input_gap_mm": front, "output_gap_mm": length - front - total,
                                   "crystal_front_mm": front, "crystal_rear_mm": front + total,
                                   "focus_depth_mm": depth, "focus_z_mm": front + depth,
                                   "active_start_mm": front + front_cap, "active_end_mm": front + front_cap + active}
        candidate["distance_scan"] = distance_scan(candidate, wl, max_l, gap_min)
        pump_positions = candidate["pump"]["positions"]
        candidate["positions"] = [
            {"id": "source", "name": "光纤出光端", "z_mm": pump_positions.get("source"), "basis": "距准直主面 f1；几何位置不依赖纤芯和 NA"},
            {"id": "collimator", "name": "已有准直平凸镜", "z_mm": pump_positions.get("collimator"), "basis": "距光纤端一个准直焦距"},
            {"id": "focus_lens", "name": "聚焦平凸镜", "z_mm": pump_positions.get("focus_lens"), "basis": f"晶体前端面前 f2−{depth:g}/n泵浦；焦点位于晶体内 {depth:g} mm"},
            {"id": "M1", "name": f"输入腔镜 M1（{mirror_label(r1)}）", "z_mm": 0, "basis": "坐标原点；HT 泵浦 / HR 激光；曲面反射面朝腔内"},
            {"id": "crystal", "name": "晶体前表面", "z_mm": front, "basis": "腔扫描设计值", "end_z_mm": front + total},
            {"id": "active", "name": "掺杂段", "z_mm": front + front_cap, "end_z_mm": front + front_cap + active, "basis": "按标签端帽/掺杂段尺寸"},
            {"id": "pump_focus", "name": "泵浦名义焦点（晶体内部）", "z_mm": front + depth, "basis": "用户指定焦点深度" if "pump_focus_depth_mm" in v else "掺杂段中心为起始方案，尚未优化吸收分布"},
            {"id": "M2", "name": f"输出耦合镜 M2（{mirror_label(candidate['R2_mm'])}）", "z_mm": length, "basis": f"距晶体后端面 {length-front-total:g} mm；ABCD 扫描设计值"},
            {"id": "terminal", "name": "受控测量与吸收终端", "z_mm": length + v.get("terminal_offset_mm", 100), "basis": "暂留 100 mm 布置空间（可调整），非光学最优距离" if "terminal_offset_mm" not in v else "用户指定终端间距"},
        ]
        max_spot = max(p["w_mm"] for p in envelope["points"])
        min_diameter = round(max(6 * max_spot, 6), 2)
        bom = []
        for role, roc, description in [("M1", r1, f"{mirror_label(r1)}输入镜；HR@{wl:g} nm / HT@{pump:g} nm；近法向，反射面朝腔内；数值 R/T 待核实"),
                                        ("M2", candidate["R2_mm"], f"{mirror_label(candidate['R2_mm'])}输出镜；部分透过@{wl:g} nm；背面 AR@{wl:g} nm 需核实")]:
            pool = [i for i in inventory if i["id"] == bindings[role]["id"]] if role in bindings else inventory
            transmission = v.get("oc_transmission_pct")
            matching = match_mirrors(pool, role=role, roc=roc, wl=wl, pump=pump, min_diameter=min_diameter,
                                     transmission=transmission if "oc_transmission_pct" in facts or role in bindings else None)
            if role == "M2" and not v.get("output_mirror_owned") and matching["matched"] and "oc_transmission_pct" not in facts and role not in bindings:
                stock_item = next(i for i in pool if i["id"] == matching["matched"][0]["id"])
                known_t = [b["value_pct"] for b in stock_item.get("coatings", []) if b["wl_min_nm"] <= wl <= b["wl_max_nm"] and b["function"] == "PR" and b.get("value_type") == "T" and b.get("comparator") == "=" and b.get("value_pct")]
                if known_t:
                    transmission = known_t[0]
            bom.append({"role": role, "spec": description, "min_clear_aperture_mm": min_diameter,
                        "transmission_pct": transmission if role == "M2" else None,
                        "transmission_basis": "用户固定" if "oc_transmission_pct" in facts else "已有实物数值未知" if v.get("output_mirror_owned") and transmission is None else "库存/起始采购方案，需通过增益和损耗进一步优化",
                        "transmission_candidates_pct": [1, 3, 5, 10] if role == "M2" else [], **matching})
            if v.get("input_mirror_owned" if role == "M1" else "output_mirror_owned"):
                bom[-1]["status"] = "owned"
                bom[-1]["coating_basis"] = "用户确认镀膜用途符合；没有据此推定具体 R/T" if v.get("mirror_coatings_user_confirmed") else "已有实物；镀膜待核实"
            if role == "M2" and transmission is None:
                bom[-1]["transmission_basis"] = "已有输出镜的 T 未知；1/3/5/10% 仅为比较场景，非实物参数"
        candidate["bom"] = bom
        candidate["components"] = []
        for role, name, spec, owned in [
            ("source", "泵浦源", f"{pump:g} nm，{v.get('pump_power_w', '待定')} W，光纤输出", "pump_power_w" in facts),
            ("collimator", "准直镜", f"f≈{candidate['pump'].get('collimator_f_mm', f1) or 0:.2f} mm；镀膜目标 AR@{pump:g} nm，实物镀膜需核对标签/曲线", bool(v.get("collimator_owned") or "collimator_f_mm" in facts or "collimator_roc_mm" in facts)),
            ("focus_lens", "聚焦镜", f"f={v.get('focus_f_mm', 0):g} mm；镀膜目标 AR@{pump:g} nm，实物镀膜需核对标签/曲线", bool(v.get("focus_lens_owned") or "focus_f_mm" in facts)),
            ("M1", "输入腔镜", bom[0]["spec"], v.get("input_mirror_owned", False)),
            ("crystal", "增益晶体", f"{v['gain_material']}，总长 {total:g} mm / 掺杂段 {active:g} mm", "crystal_length_mm" in facts),
            ("M2", "输出耦合镜", bom[1]["spec"] + (f"，T={bom[1]['transmission_pct']:g}%" if bom[1]['transmission_pct'] is not None else "，T 未知"), v.get("output_mirror_owned", False)),
            ("terminal", "测量与吸收终端", f"{wl:g} nm 测量；M2 后 {v.get('terminal_offset_mm', 100):g} mm 预留位置", False),
        ]:
            binding = bindings.get(role)
            mirror_bom = next((b for b in bom if b["role"] == role), None)
            candidate["components"].append({"role": role, "name": name, "spec": spec,
                "status": "bound" if binding else "owned" if owned else mirror_bom["status"] if mirror_bom else "purchase",
                "inventory": binding, "z_mm": next(p["z_mm"] for p in candidate["positions"] if p["id"] == role)})
        if candidate["pump"].get("image_radius_mm"):
            wp, wc = candidate["pump"]["image_radius_mm"], candidate["mode_radius_mm"]
            candidate["pump"]["size_overlap_proxy"] = (2 * wp * wc / (wp * wp + wc * wc)) ** 2
            candidate["pump"]["notes"].append("重叠指标只比较两个圆对称尺寸；不代表真实多模泵浦吸收或增益重叠效率。")
            if wp < wc / 3 or wp > wc * 3:
                candidate["pump"]["notes"].append(f"当前成像半径 {wp*1000:.1f} μm 与腔模 {wc*1000:.1f} μm 相差超过 3 倍；保留现有透镜的方案存在模式尺寸失配。先确认实际 808 nm 出光尺寸，再改变 f2/f1 倍率。")
                candidate["pump"]["size_mismatch"] = True
    result["candidates"] = chosen
    selected = min(int(v.get("candidate_rank", 1)), len(chosen))
    result["selected_rank"] = selected
    recommended = chosen[selected - 1]
    for key in recommended["pump"]["missing"]:
        question = {
            "collimator_f_mm": "R50 准直镜的实际焦距，或玻璃材料在泵浦波长下的折射率是多少？",
            "focus_f_mm": "聚焦镜焦距是多少？", "fiber_core_um": "光纤芯径是多少 μm？",
            "fiber_na": "光纤 NA 是多少？", "pump_source": "是否为光纤输出？自由空间源需另建输入光束模型。",
        }[key]
        ask(key, question, "用于收敛泵浦光斑与通光口径的不确定性；当前几何坐标和腔镜仿真继续有效。")
    if not v.get("pump_power_w"):
        ask("pump_power_w", "泵浦最大功率是多少？", "用于器件承载与后续热模型；当前不预测热焦距。")
    if r1 is not None:
        issues.append({"level": "verify", "text": "凹面 M1 的腔内反射已按实际曲率计算；808 nm 透射还缺基底两面和厚度。泵浦图暂是忽略 M1 折射的对照基线，实际焦点须测透过 M1 后的焦散或补齐参数再算。"})
    if v.get("output_mirror_owned") and v.get("oc_transmission_pct") is None:
        issues.append({"level": "verify", "text": "已有输出镜 T@1064 未知；保留实物并继续腔模计算，不将 5% 场景当成实物透过率。"})
    result["threshold_scan"] = [
        {"T_pct": t, "round_trip_loss_pct": loss * 100,
         "required_gain_cm_inv": round(-math.log(0.999 * (1 - t / 100) * (1 - loss)) / (2 * active / 10), 6)}
        for t in sorted({t for t in [1, 3, 5, 10, v.get("oc_transmission_pct")] + [c["bom"][1]["transmission_pct"] for c in chosen] if t is not None})
        for loss in [0.005, 0.01, 0.02]
    ]
    assumptions.append({"name": "输出耦合扫描", "value": "R1=99.9%；其余往返损耗=0.5/1/2%", "basis": "仅计算阈值所需增益 g=-ln(R1·R2·(1−L))/(2l)，不是最佳 T 或起振功率预测。"})
    assumptions.append({"name": "采购规格核验", "value": "R/T 数值为目标规格", "basis": "库存 HR/HT 标签只用于初筛；还需供应商数据核对反射/透射率、有效口径、入射角、偏振、面形、基底与承载能力。"})
    assumptions.append({"name": "热透镜扫描", "value": "∞、2000…50 mm", "basis": "在晶体几何中心插入会聚薄透镜、往返两次；场景敏感性分析，未从 6 W 或其他泵浦功率推算实际热透镜。"})
    result["status"] = "preliminary" if missing or recommended["pump"]["status"] != "geometric_model" else "modeled"
    placement = recommended["placement"]
    output_t = recommended['bom'][1]['transmission_pct']
    result["summary"] = (f"已扫描 {evaluated} 个几何，M1 {mirror_label(r1)}、M2 {mirror_label(recommended['R2_mm'])}；输出镜 T=" + (f"{output_t:g}%" if output_t is not None else "未知") + "。"
        f"M1 距晶体前端面 {placement['input_gap_mm']:g} mm；M2 距晶体后端面 {placement['output_gap_mm']:g} mm；两镜间距 {recommended['length_mm']:g} mm。"
        "腔内位置、腔模与 M2 距离扫描已计算；假设与实物条件分别列出。")
    if recommended["pump"].get("baseline_only"):
        result["summary"] += "泵浦位置仅为未计 M1 透射折射的对照基线，不能作为实际安装定位。"
    result["optimization"] = {"claim": "已知约束及列明假设下的综合最优候选", "score": recommended["score"],
                              "not_solved": ["吸收/增益饱和与输出功率最优值", "实际热透镜与冷却边界", "真实泵浦场与高阶横模竞争"],
                              "target_mode_radius_um": assumed_target * 1000,
                              "owned_lenses_preserved": True}
    result["next_steps"] = [
        "逐项核对事实卡，纠正标签识别；补充下方关键问题后重新计算。",
        "比较候选曲率与热透镜扫描，再核对库存条目的原始镀膜、可用数量与口径。",
        "测得 808 nm 透射、泵浦像尺寸与腔内损耗后再定输出耦合率；当前只提供候选规格。",
        "确认镜架、晶体夹持/冷却、透镜主面、测量器件额定功率与吸收终端后，才进入实验室批准的受控验证。",
    ]
    return result
