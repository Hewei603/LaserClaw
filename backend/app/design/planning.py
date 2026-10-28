"""Resolve owned parts, inventory and design assumptions without rewriting facts."""
from __future__ import annotations

import math
import re
from collections import Counter

BK7_SOURCE = "https://media.schott.com/api/public/content/41e799d0bf874807a0bb8e702fbb75b5?v=54856406"
CRYSTAL_SOURCE = "https://www.crystech.com/Laser_Crystal/446.html"


def bk7_index(wavelength_nm):
    l2 = (wavelength_nm / 1000) ** 2
    return math.sqrt(1 + sum(b * l2 / (l2 - c) for b, c in [
        (1.03961212, .00600069867), (.231792344, .0200179144), (1.01046945, 103.560653)]))


def resolve_inputs(facts, inventory):
    values = {key: fact["value"] for key, fact in facts.items()}
    assumptions, issues, bindings = [], [], {}
    lookup = {row["id"]: row for row in inventory}

    def propose(key, value, label, basis, source=None):
        if key in values:
            return
        values[key] = value
        assumptions.append({"key": key, "name": label, "value": value, "basis": basis,
                            **({"source": source} if source else {})})

    # Explicit assignments are hard constraints, not just a bonus in the ranking.
    counts = Counter(int(v) for k, v in values.items() if k.endswith("_inventory_id"))
    for role, category in [("collimator", "lens"), ("focus_lens", "lens"), ("M1", "mirror"),
                            ("M2", "mirror"), ("crystal", "gain_crystal")]:
        iid = values.get(f"{role}_inventory_id")
        if not iid:
            continue
        item = lookup.get(int(iid))
        if not item or item["category"] != category or item["condition"] == "damaged" or item["available_quantity"] < counts[int(iid)]:
            issues.append({"level": "blocking", "text": f"指定 {role} 库存 #{int(iid)} 不存在、类别不符、已损坏或数量不足；解除绑定或更换元件后再计算。"})
            continue
        bindings[role] = {"id": item["id"], "name": item["name"], "mode": "locked", "raw_spec": item.get("raw_spec")}
        if role in {"collimator", "focus_lens"}:
            key = "collimator_f_mm" if role == "collimator" else "focus_f_mm"
            focal = item.get("focal_length_mm")
            if focal and focal > 0:
                if key in values and not math.isclose(values[key], focal, rel_tol=.01):
                    issues.append({"level": "blocking", "text": f"{role} 的指定库存焦距 {focal:g} mm 与已记录 {values[key]:g} mm 冲突。"})
                else:
                    propose(key, focal, f"{role} 库存焦距", f"来自指定库存 #{item['id']}：{item['name']}。")
            else:
                issues.append({"level": "blocking", "text": f"指定 {role} 没有可用的正焦距，不能替该元件猜一个焦距。"})
        if role in {"M1", "M2"}:
            prefix = "input" if role == "M1" else "output"
            roc = item.get("roc_mm")
            flat = bool(item.get("roc_is_flat"))
            if not flat and (not roc or roc <= 0):
                issues.append({"level": "blocking", "text": f"指定 {role} 需要明确平面或正曲率凹面；未知曲率不能替代。"})
            elif (flat and values.get(f"{prefix}_roc_mm")) or (f"{prefix}_mirror_flat" in values and values[f"{prefix}_mirror_flat"] != flat) or (not flat and f"{prefix}_roc_mm" in values and not math.isclose(values[f"{prefix}_roc_mm"], roc, rel_tol=.01)):
                issues.append({"level": "blocking", "text": f"指定 {role} 库存的曲率与固定曲率约束冲突。"})
            else:
                propose(f"{prefix}_mirror_flat", flat, f"{role} 库存面形", f"锁定库存 #{item['id']}，只优化位置。")
                if not flat:
                    propose(f"{prefix}_roc_mm", roc, f"{role} 库存曲率", f"锁定库存 #{item['id']}，只优化位置。")
        if role == "M2":
            for band in item.get("coatings", []):
                if (band["function"] == "PR" and band["wl_min_nm"] <= values.get("laser_wavelength_nm", 0) <= band["wl_max_nm"]
                        and band.get("value_type") == "T" and band.get("comparator") == "=" and band.get("value_pct")):
                    propose("oc_transmission_pct", band["value_pct"], "M2 库存透过率", f"库存 #{item['id']} 的标称 T；不是 R 的无损换算。")
        if role == "crystal":
            for key, field in [("gain_material", "material"), ("crystal_length_mm", "thickness_mm"),
                               ("cut_axis", "cut_axis"), ("doping_pct", "doping_pct")]:
                if item.get(field) is not None:
                    if key in values and values[key] != item[field]:
                        issues.append({"level": "blocking", "text": f"指定晶体库存的 {field} 与已有条件冲突。"})
                    else:
                        propose(key, item[field], "晶体库存参数", f"来自指定库存 #{item['id']} 的 {field}。")

    if values.get("pump_wavelength_nm") and values.get("laser_wavelength_nm"):
        propose("cavity_type", "linear", "腔型方案", "未固定腔型时，先设计端泵直线腔。")
        propose("pump_source", "fiber", "泵浦出光方案", "未指定出光方式时，先以光纤耦合泵浦和双透镜成像设计。")
    # A missing crystal can be a procurement decision. Never resize an existing crystal.
    known_crystal = any(k in values for k in ["crystal_length_mm", "active_length_mm", "crystal_part", "crystal_inventory_id"])
    if not known_crystal:
        for item in inventory:
            if (item["category"] != "gain_crystal" or item["condition"] != "ok" or item["available_quantity"] < 1
                    or (item.get("material") or "").lower().replace(" ", "") != str(values.get("gain_material", "?")).lower().replace(" ", "")):
                continue
            dimensions = item.get("dimensions") or ""
            match = re.fullmatch(r"\s*(\d+(?:\.\d+)?)\s*[*×xX]\s*(\d+(?:\.\d+)?)\s*[*×xX]\s*(\d+(?:\.\d+)?)\s*(?:mm(?:3|³|\^3)?)?\s*", dimensions)
            if not match or not all(float(x) > 0 for x in match.groups()):
                continue
            width, height, length = map(float, match.groups())
            for key, value in {"crystal_width_mm": width, "crystal_height_mm": height, "crystal_length_mm": length,
                               "active_length_mm": length, "front_cap_mm": 0, "rear_cap_mm": 0}.items():
                propose(key, value, "库存晶体方案", f"优先采用可用库存 #{item['id']}：{dimensions}；暂按整段均匀掺杂，复合结构需核对标签。")
            bindings["crystal"] = {"id": item["id"], "name": item["name"], "mode": "proposed", "raw_spec": item.get("raw_spec")}
            known_crystal = True
            break
    if "yvo4" in str(values.get("gain_material", "")).lower() and not known_crystal:
        for key, value in {"crystal_length_mm": 10, "active_length_mm": 10, "front_cap_mm": 0,
                           "rear_cap_mm": 0, "crystal_width_mm": 3, "crystal_height_mm": 3, "doping_pct": .3}.items():
            propose(key, value, "待购晶体参考规格", "先用厂家 3×3×10 mm、0.30% Nd:YVO4 规格建立候选；这是采购方案，不是用户已有晶体。", CRYSTAL_SOURCE)
        propose("ar_wavelengths_nm", [808, 1064], "待购晶体镀膜", "采购目标双面 AR808/1064。", CRYSTAL_SOURCE)
    if "active_length_mm" not in values and "crystal_length_mm" in values and "crystal_part" not in values:
        propose("active_length_mm", values["crystal_length_mm"] - values.get("front_cap_mm", 0) - values.get("rear_cap_mm", 0),
                "掺杂长度假设", "未描述复合结构时，暂按总长扣除已知端帽；需用标签核验。")

    pump = values.get("pump_wavelength_nm", 808)
    used = Counter(int(b["id"]) for b in bindings.values())
    for role, field, owned in [("collimator", "collimator_f_mm", "collimator_owned"), ("focus_lens", "focus_f_mm", "focus_lens_owned")]:
        if role in bindings or field in values or values.get(owned) or (role == "collimator" and values.get("collimator_roc_mm")):
            continue
        options = [item for item in inventory if item["category"] == "lens" and item["condition"] == "ok"
                   and item["available_quantity"] > used[item["id"]] and (item.get("focal_length_mm") or 0) > 0
                   and any(b["wl_min_nm"] <= pump <= b["wl_max_nm"] and b["function"] in {"AR", "HT"} for b in item.get("coatings", []))]
        if options:
            item = min(options, key=lambda r: abs(math.log(r["focal_length_mm"] / 100)))
            propose(field, item["focal_length_mm"], f"{role} 库存选型", f"优先选可用、泵浦波段镀膜匹配的库存 #{item['id']}。")
            bindings[role] = {"id": item["id"], "name": item["name"], "mode": "proposed", "raw_spec": item.get("raw_spec")}
            used[item["id"]] += 1
        else:
            propose(field, 100, f"{role} 待购焦距", "库存没有匹配件，先采用 f=100 mm 的采购方案；孔径由泵浦参数约束。")

    if values.get("collimator_roc_mm") and not values.get("collimator_f_mm"):
        propose("collimator_index", bk7_index(pump), "R50 透镜材料假设", "按 N-BK7 的 Sellmeier 色散估算，实际材料/主面不同会改变位置；该值不写入事实卡。", BK7_SOURCE)
    if values.get("collimator_owned") and not values.get("collimator_f_mm") and not values.get("collimator_roc_mm"):
        propose("collimator_f_mm", 100, "已有准直镜焦距假设", "没有任何曲率或焦距信息，暂用 100 mm 做位置方案。")
    if values.get("focus_lens_owned") and not values.get("focus_f_mm"):
        propose("focus_f_mm", 100, "已有聚焦镜焦距假设", "暂按 100 mm 建模，实物焦距确认后自动重算。")
    if values.get("input_mirror_near_crystal") and "crystal_front_mm" not in values:
        propose("crystal_front_mm", 3, "输入镜近晶体间隙", "将“靠近”实现为 3 mm 镀膜面到前端面间隙；可按镜架尺寸修改，不是机械接触。")
    if not values.get("output_mirror_owned"):
        propose("oc_transmission_pct", 5, "输出耦合率起始方案", "先选 T=5% 并比较 1/3/5/10% 的阈值；缺少增益/损耗时不声称功率最优。")
    for prefix in ("input", "output"):
        if values.get(f"{prefix}_mirror_flat") and values.get(f"{prefix}_roc_mm"):
            issues.append({"level": "blocking", "text": f"{prefix} 镜同时固定为平面和有限曲率，请解除已过时的曲率条件。"})
        if values.get(f"{prefix}_mirror_flat") is False and not values.get(f"{prefix}_roc_mm"):
            issues.append({"level": "blocking", "text": f"{prefix} 镜已固定为曲面，但尚无曲率。"})
    propose("min_output_gap_mm", 5, "M2 最小装配间隙", "先给镜架留 5 mm，固定距离或真实机械限制优先。")
    return values, assumptions, issues, bindings
