# -*- coding: utf-8 -*-
"""Live acceptance: does the AI plan actually USE the physics kernel's numbers?

The scenario is the one that matters in a real lab: the user knows what they
want and almost nothing about the geometry.  They give a wavelength, a pump, a
crystal and a power goal — no mirrors, no cavity length, no angles.

For the plan to be buildable, LaserClaw must:

  1. search a cavity geometry constrained to mirrors the lab actually owns,
  2. measure its thermal-lens margin (not guess it from |m|),
  3. compute the LBO phase-matching angle from Sellmeier data,
  4. hand all of that to the model, and
  5. have the model write the plan around those numbers instead of inventing.

Step 5 is what this script checks that the unit tests cannot: it needs a real
provider.  Run it with a configured key:

    py scripts/acceptance_kernel_grounded_plan.py
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import create_engine  # noqa: E402
from sqlalchemy.orm import sessionmaker  # noqa: E402
from sqlalchemy.pool import StaticPool  # noqa: E402

from app.config import get_settings  # noqa: E402
from app.database import Base, get_db  # noqa: E402
from app import models  # noqa: E402,F401
from app.main import app  # noqa: E402
from app.models.inventory import InventoryItem  # noqa: E402

OK, BAD, WARN = "[PASS]", "[FAIL]", "[WARN]"

# What the user actually says. Deliberately thin: no mirrors, no length, no angle.
CASE = {
    "title": "808nm 泵浦 Nd:YAG，腔内 LBO 倍频 532nm",
    "cavity_type": "linear",
    "goal": "搭一台连续 532nm 绿光源，输出 >1W，告诉我用哪两块镜子、腔长多少、"
            "晶体放在哪、LBO 切角多少。我只有下面库存里的镜子。",
    "parameters": {
        "wavelength_nm": 1064,
        "pump_nm": 808,
        "gain_medium": "Nd:YAG",
        "crystal": {"n": 1.8147, "thickness_mm": 10, "position_mm": 20},
        "nonlinear_crystal": "lbo",
        "shg_pm_type": "I",
        "target_output_w": 1.0,
    },
}

# The lab's mirror stock — the search must not step outside this.
STOCK_ROCS = [("flat", True, None), ("R=100mm", False, 100.0),
              ("R=200mm", False, 200.0), ("R=500mm", False, 500.0)]


def _numbers(text: str) -> set[float]:
    return {float(m) for m in re.findall(r"\d+\.?\d*", text)}


def main() -> int:
    settings = get_settings()
    print(f"provider = {settings.ai_provider}, model = {settings.openai_model}")
    if settings.ai_provider == "mock":
        print(f"{BAD} AI_PROVIDER=mock — 这个脚本必须用真实 provider 才有意义")
        return 2

    engine = create_engine("sqlite://", connect_args={"check_same_thread": False},
                           poolclass=StaticPool)
    Session = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    Base.metadata.create_all(bind=engine)
    db = Session()

    for name, is_flat, roc in STOCK_ROCS:
        db.add(InventoryItem(name=f"腔镜 {name}", category="mirror", quantity=2,
                             roc_mm=roc, roc_is_flat=is_flat, condition="good"))
    db.commit()

    app.dependency_overrides[get_db] = lambda: db
    from fastapi.testclient import TestClient
    client = TestClient(app)

    case_id = client.post("/api/cases", json=CASE).json()["id"]
    print(f"\n案例已建 (id={case_id})，用户只给了波长/晶体/功率目标，没给任何镜子和腔长\n")

    resp = client.post(f"/api/cases/{case_id}/generate-plan", json={"use_rag": False})
    if resp.status_code != 200:
        print(f"{BAD} generate-plan 失败: {resp.status_code} {resp.text[:400]}")
        return 1
    content = resp.json()["content"]
    physics = content.get("computed_physics") or {}

    failures = 0

    # --- 1. the kernel ran, and ran the right tools ---------------------------
    print("=" * 78)
    print("  1  物理内核是否真的跑了")
    print("=" * 78)
    tools = physics.get("tools_run") or []
    print(f"tools_run = {tools}")
    if physics.get("skipped"):
        print(f"{WARN} skipped = {physics['skipped']}")
    for needed in ("cavity_design_search", "phase_match:SHG"):
        if needed in tools:
            print(f"{OK} {needed} 已执行")
        else:
            print(f"{BAD} {needed} 没有执行")
            failures += 1

    search = (physics.get("results") or {}).get("cavity_design_search") or {}
    rec = search.get("recommended") or {}
    pm = ((physics.get("results") or {}).get("phase_matching") or {}).get("SHG") or {}

    # --- 2. the searched geometry is buildable from THIS lab's stock ----------
    print("\n" + "=" * 78)
    print("  2  搜出来的几何是否可搭建（且只用库存镜子）")
    print("=" * 78)
    if not rec:
        print(f"{BAD} 没有搜出任何几何")
        return 1
    print(f"推荐: R1={rec['R1']}  R2={rec['R2']}  L={rec['length_mm']} mm  "
          f"w0={rec['waist_w0_mm']} mm")
    print(f"热透镜裕度: {rec.get('thermal_lens_tolerance_dioptre')} D "
          f"(即 f>={rec.get('thermal_lens_tolerance_min_f_mm')} mm 时仍稳定)")
    print(f"搜索空间: {search['search_space']['roc_source']}, "
          f"{search['search_space']['geometries_evaluated']} 个几何, "
          f"{search['search_space']['stable_configurations_found']} 个稳定解")
    print("元件位置:")
    for p in rec.get("element_placement", []):
        print(f"    {p['position_mm']:>7} mm  {p['element']}")

    allowed = {"flat"} | {f"R={r:g}mm" for _, _, r in STOCK_ROCS if r}
    if {rec["R1"], rec["R2"]} <= allowed:
        print(f"{OK} 只用了库存里的曲率 {sorted(allowed)}")
    else:
        print(f"{BAD} 用了库存没有的镜子: {rec['R1']}, {rec['R2']}")
        failures += 1
    if search["search_space"]["roc_source"] == "lab inventory":
        print(f"{OK} 搜索被约束到实验室库存")
    else:
        print(f"{BAD} 没有使用库存约束 (roc_source={search['search_space']['roc_source']})")
        failures += 1
    if (rec.get("thermal_lens_tolerance_dioptre") or 0) > 0:
        print(f"{OK} 热稳健性是实测的，不是 |m| 代理")
    else:
        print(f"{BAD} 推荐腔承受不了任何热透镜")
        failures += 1

    # --- 3. phase matching from Sellmeier, not from the model ----------------
    print("\n" + "=" * 78)
    print("  3  倍频角是否由 Sellmeier 算出")
    print("=" * 78)
    if pm.get("solutions"):
        sol = pm["solutions"][0]
        print(f"LBO type-{pm['type']} 1064->532: theta={sol['theta_deg']} deg, "
              f"phi={sol.get('phi_deg')} deg")
        print(f"{OK} 相位匹配角来自确定性计算")
    else:
        print(f"{BAD} 没有算出相位匹配角")
        failures += 1

    # --- 4. does the MODEL's prose use those numbers? ------------------------
    print("\n" + "=" * 78)
    print("  4  模型写出来的计划，数字是否真的来自内核")
    print("=" * 78)
    prose_no_physics = json.dumps(
        {k: v for k, v in content.items() if k != "computed_physics"}, ensure_ascii=False)
    said = _numbers(prose_no_physics)

    checks = [
        ("腔长 L", rec["length_mm"]),
        ("LBO 切角 theta", pm["solutions"][0]["theta_deg"] if pm.get("solutions") else None),
    ]
    for label, value in checks:
        if value is None:
            continue
        hit = any(abs(n - value) <= max(0.5, abs(value) * 0.01) for n in said)
        if hit:
            print(f"{OK} 计划正文引用了内核算出的 {label} = {value}")
        else:
            print(f"{BAD} 计划正文没有出现内核的 {label} = {value}（可能自己编了数）")
            failures += 1

    cp = content.get("computed_parameters")
    if cp:
        print(f"{OK} 模型填写了 computed_parameters 字段:")
        print("     " + json.dumps(cp, ensure_ascii=False)[:400])
    else:
        print(f"{WARN} 模型没有填 computed_parameters（提示词要求填）")

    # A plan that never mentions mirrors/placement is not buildable.
    for kw in ("腔长", "晶体", "镜"):
        if kw in prose_no_physics:
            print(f"{OK} 计划提到了「{kw}」")
        else:
            print(f"{WARN} 计划没提到「{kw}」")

    print("\n" + "=" * 78)
    print("  生成的实验计划正文（截断）")
    print("=" * 78)
    for key in ("summary", "objective", "steps", "computed_parameters", "risks"):
        if key in content:
            print(f"\n--- {key} ---")
            v = content[key]
            text = json.dumps(v, ensure_ascii=False, indent=2) if not isinstance(v, str) else v
            print(text[:1600])

    print("\n" + "=" * 78)
    print(f"  结论: {'全部通过' if failures == 0 else str(failures) + ' 项不合格'}")
    print("=" * 78)
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
