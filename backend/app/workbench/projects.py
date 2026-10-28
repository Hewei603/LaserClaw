"""Case-owned optical projects. Every edit saves a new, reproducible revision."""
from threading import RLock
from uuid import uuid4

from pydantic import Field, model_validator

from ..models import GeneratedContent, InventoryItem
from .optics import OpticalSystem, StrictInput, analyze_system

_lock = RLock()


class Part(StrictInput):
    element_index: int = Field(ge=0)
    role: str = ""
    ownership: str = "proposed"
    inventory_id: int | None = None
    source: str = Field(min_length=1)
    locked_parameters: list[str] = Field(default_factory=list)
    unknowns: list[str] = Field(default_factory=list)


class OpticalProject(StrictInput):
    title: str = Field(min_length=1, max_length=200)
    system: OpticalSystem
    parts: list[Part] = Field(default_factory=list)
    assumptions: list[str] = Field(default_factory=list)
    notes: str = ""

    @model_validator(mode="after")
    def indices(self):
        uids = set()
        for element in self.system.elements:
            if not element.uid:
                element.uid = str(uuid4())
            if element.uid in uids:
                raise ValueError("Element identities must be unique")
            uids.add(element.uid)
        seen = set()
        for part in self.parts:
            if part.element_index >= len(self.system.elements) or part.element_index in seen:
                raise ValueError("Part index missing from system or duplicated")
            seen.add(part.element_index)
            fields = self.system.elements[part.element_index].model_dump()
            if any(key not in fields for key in part.locked_parameters):
                raise ValueError("Locked parameter is not an element property")
        return self


class SaveProject(StrictInput):
    base_revision_id: int | None = None
    project: OpticalProject
    change_note: str = Field(min_length=1, max_length=2000)
    unlock_quote: str = Field(default="", description="Only when explicitly authorized to change locked hardware: literal quote from current user request.")


class ReadProject(StrictInput):
    revision_id: int | None = None


def revisions(db, case_id):
    return db.query(GeneratedContent).filter_by(case_id=case_id, content_type="optical_project").order_by(GeneratedContent.id.desc()).all()


def read_project(db, case_id, revision_id=None):
    row = db.get(GeneratedContent, revision_id) if revision_id else db.query(GeneratedContent).filter_by(case_id=case_id, content_type="optical_project").order_by(GeneratedContent.id.desc()).first()
    if row is None:
        if revision_id:
            raise ValueError("Project revision does not exist")
        return None
    if row.case_id != case_id or row.content_type != "optical_project":
        raise ValueError("Project revision does not belong to this case")
    return {"revision_id": row.id, **row.content}


def save_project(db, case_id, args, *, allow_unlock=False):
    project = args.project
    with _lock:
        previous = read_project(db, case_id)
        if args.base_revision_id != (previous["revision_id"] if previous else None):
            raise ValueError("Project changed since it was read. Reload latest revision before saving; no data was overwritten.")
        if previous and not allow_unlock:
            before = previous["project"]
            new_parts = {p.element_index: p for p in project.parts}
            for part in before["parts"]:
                if not part["locked_parameters"]:
                    continue
                old_element = before["system"]["elements"][part["element_index"]]
                idx = next((i for i, e in enumerate(project.system.elements) if e.uid == old_element["uid"]), None)
                if idx is None or idx not in new_parts:
                    raise ValueError("Cannot remove a locked part without explicit unlock")
                now = project.system.elements[idx].model_dump()
                if new_parts[idx].role != part["role"] or new_parts[idx].inventory_id != part["inventory_id"]:
                    raise ValueError("Cannot change locked part role or inventory binding")
                for key in part["locked_parameters"]:
                    if key not in new_parts[idx].locked_parameters or now[key] != old_element[key]:
                        raise ValueError(f"Locked hardware parameter changed: element {idx}, {key}")
        for part in project.parts:
            if part.inventory_id is not None and db.get(InventoryItem, part.inventory_id) is None:
                raise ValueError("Inventory binding does not exist")
        output = analyze_system(project.system)
        data = {"project": project.model_dump(), "analysis": output, "parent_revision_id": args.base_revision_id,
                "change_note": args.change_note, "summary": project.title}
        row = GeneratedContent(case_id=case_id, content_type="optical_project", content=data, prompt_version="optical-project-v1")
        db.add(row)
        db.commit()
        return {"status": "completed", "revision_id": row.id, **data}


def project_from_design(design, candidate, previous=None):
    """Preserve M1/M2 roles and physical crystal segments when importing a design."""
    v = design["resolved_inputs"]
    crystal = candidate["crystal"]
    front, total, n = crystal["position_mm"], crystal["thickness_mm"], crystal["n"]
    material = v.get("gain_material", "增益晶体")
    cap = "YVO4" if "yvo4" in material.lower() else "无掺杂"
    crystal_owned = any(key in design.get("facts", {}) for key in ("crystal_part", "crystal_length_mm", "active_length_mm", "crystal_inventory_id"))
    elements = [{"name": "M1 输入镜", "kind": "mirror", "radius_mm": candidate.get("R1_mm")},
                {"name": "M1 → 晶体前端面", "kind": "space", "length_mm": front},
                {"name": f"{cap} 前端帽", "kind": "space", "length_mm": v.get("front_cap_mm", 0), "n": n},
                {"name": f"{material} 掺杂段", "kind": "space", "length_mm": v["active_length_mm"], "n": n},
                {"name": f"{cap} 后端帽", "kind": "space", "length_mm": v.get("rear_cap_mm", 0), "n": n},
                {"name": "晶体后端面 → M2", "kind": "space", "length_mm": candidate["length_mm"]-front-total},
                {"name": "M2 输出镜", "kind": "mirror", "radius_mm": candidate["R2_mm"]}]
    parts = []
    for idx, prefix, role in ((0, "input", "pump_input"), (6, "output", "laser_output")):
        inventory_id = v.get(f"{'M1' if idx == 0 else 'M2'}_inventory_id")
        owned = v.get(f"{prefix}_mirror_owned") or inventory_id is not None
        part = {"element_index": idx, "role": role, "ownership": "owned" if owned else "proposed",
                "source": "用户确认已有腔镜" if owned else "设计候选", "locked_parameters": ["kind", "radius_mm", "aoi_deg"] if owned else [],
                "unknowns": ["镀膜具体 R/T、基底和口径待核实"]}
        if prefix == "input" and candidate.get("R1_mm"):
            part["unknowns"].append("泵浦透射需要 M1 两面曲率、厚度和折射率；此工程仅为腔内 1064 nm 模型")
        if inventory_id is not None:
            part["inventory_id"] = int(inventory_id)
        parts.append(part)
    for idx in (2, 3, 4):
        parts.append({"element_index": idx, "role": "crystal", "ownership": "owned" if crystal_owned else "proposed",
                      "source": "已有晶体尺寸；折射率采用列明模型" if crystal_owned else "设计提出的晶体尺寸，尚未确认为实物",
                      "inventory_id": int(v["crystal_inventory_id"]) if v.get("crystal_inventory_id") else None,
                      "locked_parameters": ["kind", "length_mm"] if crystal_owned else [], "unknowns": []})
    if previous:
        old = previous["project"]
        for part in parts:
            matches = [p for p in old["parts"] if p["role"] == part["role"] and (part["role"] != "crystal" or old["system"]["elements"][p["element_index"]]["name"] == elements[part["element_index"]]["name"])]
            if len(matches) == 1:
                elements[part["element_index"]]["uid"] = old["system"]["elements"][matches[0]["element_index"]]["uid"]
    return OpticalProject(title=f"{v['laser_wavelength_nm']:g} nm 腔内光学工程 · M1/M2 实物约束", system={"mode": "standing_wave", "wavelength_nm": v["laser_wavelength_nm"], "elements": elements},
                          parts=parts, assumptions=["冷腔、近轴正入射；不计算增益饱和或输出功率。", "晶体折射率按当前偏振模型；未实测热透镜。"],
                          notes="z=0 为 M1 腔内反射面，沿 M1→M2 展开，距离单位 mm。腔内模型不包含输入镜的泵浦透射，也不预测输出镜背面的出射传播。")
