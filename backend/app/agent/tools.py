"""Agent tool registry and executable tools."""
from __future__ import annotations

from time import perf_counter
from typing import Any, Callable

from sqlalchemy.orm import Session

from ..knowledge.retrieval import results_to_citations, search_case_and_global_knowledge
from ..models import AgentTask, AgentToolCall, CaseComponentItem, CaseModule, ExperimentCase, GeneratedContent
from ..physics.toolkit import run_cavity_design, run_coating_tmm, run_phase_match


def tool_schemas() -> list[dict[str, Any]]:
    """Return public tool schemas for inspection and Agent prompting."""
    return [
        {"name": "get_case", "description": "Read an experiment case.", "input_schema": {"required": ["case_id"]}},
        {"name": "list_generated_contents", "description": "List prior generated artifacts.", "input_schema": {"required": ["case_id"]}},
        {"name": "list_attachments", "description": "List case attachments.", "input_schema": {"required": ["case_id"]}},
        {"name": "list_case_modules", "description": "List optional modules attached to a case.", "input_schema": {"required": ["case_id"]}},
        {"name": "create_case_module", "description": "Create a case module for stability, beam, spectrum, or component workflows.", "input_schema": {"required": ["case_id", "module_type"]}},
        {"name": "run_case_module_analysis", "description": "Run a case module analysis or generation workflow.", "input_schema": {"required": ["module_id"]}},
        {"name": "list_component_items", "description": "List component/procurement items for a case.", "input_schema": {"required": ["case_id"]}},
        {"name": "compute_cavity_design", "description": "Deterministic ABCD/Gaussian cavity analysis or length-scan design (stability, waist, spot sizes, element placement).", "input_schema": {"required": ["R1_mm", "R2_mm"]}},
        {"name": "compute_phase_match", "description": "Deterministic phase-matching solve (SHG/SFG angles, walk-off) for BBO/LBO/KTP/BiBO.", "input_schema": {"required": ["crystal", "lambda1_nm"]}},
        {"name": "match_components", "description": "Deterministic inventory matching: requirement spec -> per-candidate structured verdicts with dominance frontier.", "input_schema": {"required": ["surfaces"]}},
        {"name": "compute_coating_tmm", "description": "Deterministic thin-film coating evaluation (exact stack, vendor curve, or honest nominal-label archetype).", "input_schema": {"required": []}},
        {"name": "analyze_power_curve", "description": "Fit threshold + slope efficiency from measured pump/output power data; cross-series Findlay-Clay/Caird loss analysis.", "input_schema": {"required": []}},
        {"name": "search_knowledge", "description": "Search indexed cases, attachments, and generated content.", "input_schema": {"required": ["query"]}},
        {"name": "search_similar_cases", "description": "Search case sources with similar symptoms and cavity type.", "input_schema": {"required": ["query"]}},
        {"name": "save_generated_content", "description": "Persist an Agent artifact.", "input_schema": {"required": ["case_id", "content_type", "content"]}},
    ]


def record_tool_call(
    db: Session,
    task: AgentTask,
    step_id: int | None,
    tool_name: str,
    input_json: dict[str, Any],
    runner: Callable[[], dict[str, Any]],
) -> dict[str, Any]:
    started = perf_counter()
    call = AgentToolCall(task_id=task.id, step_id=step_id, tool_name=tool_name, input_json=input_json)
    db.add(call)
    try:
        output = runner()
        call.output_json = output
        call.status = "completed"
        return output
    except Exception as exc:
        call.status = "failed"
        call.error_message = str(exc)
        raise
    finally:
        call.latency_ms = int((perf_counter() - started) * 1000)


def get_case_payload(case: ExperimentCase) -> dict[str, Any]:
    return {
        "id": case.id,
        "title": case.title,
        "description": case.description,
        "cavity_type": case.cavity_type,
        "goal": case.goal,
        "parameters": case.parameters or {},
        "symptoms": case.symptoms or [],
    }


def search_payload(db: Session, query: str, case_id: int | None, top_k: int, task_id: int | None) -> dict[str, Any]:
    run, results = search_case_and_global_knowledge(db, query=query, case_id=case_id, top_k=top_k, task_id=task_id)
    return {
        "retrieval_run_id": run.id,
        "confidence": run.confidence,
        "no_answer": bool(run.no_answer),
        "max_score": round(run.max_score or 0.0, 4),
        "message": (run.filters_json or {}).get("low_confidence_message"),
        "results": [result.model_dump() for result in results],
        "citations": results_to_citations(results),
    }


def list_generated_contents_payload(case: ExperimentCase) -> dict[str, Any]:
    return {
        "items": [
            {
                "id": item.id,
                "content_type": item.content_type,
                "generated_at": item.generated_at.isoformat() if item.generated_at else None,
            }
            for item in case.generated_contents
        ]
    }


def list_attachments_payload(case: ExperimentCase) -> dict[str, Any]:
    return {
        "items": [
            {
                "id": attachment.id,
                "filename": attachment.filename,
                "file_type": attachment.file_type,
            }
            for attachment in case.attachments
        ]
    }


def list_case_modules_payload(case: ExperimentCase) -> dict[str, Any]:
    return {
        "items": [
            {
                "id": item.id,
                "module_type": item.module_type,
                "title": item.title,
                "status": item.status,
                "config_json": item.config_json or {},
                "result_json": item.result_json or {},
            }
            for item in case.case_modules
        ]
    }


def run_physics_tool_payload(module_type: str, config: dict[str, Any]) -> dict[str, Any]:
    """Dispatch a physics module type to its deterministic compute adapter."""
    if module_type == "cavity_design":
        return run_cavity_design(config)
    if module_type == "phase_match":
        return run_phase_match(config)
    if module_type == "coating_tmm":
        return run_coating_tmm(config)
    return {"status": "failed", "message": f"Unknown physics tool '{module_type}'"}


def create_case_module_payload(db: Session, case: ExperimentCase, module_type: str, title: str | None = None) -> dict[str, Any]:
    labels = {
        "stability": "Stability measurement",
        "beam_profile": "Beam profile analysis",
        "spectrum": "Spectrum analysis",
        "components": "Case component list",
        "module_management": "Case module",
        "cavity_design": "Cavity design (ABCD)",
        "phase_match": "Phase matching",
        "coating_tmm": "Coating TMM analysis",
        "component_match": "Component matching (inventory)",
        "power_curve": "Power transfer curve (threshold & slope)",
    }
    normalized_type = "components" if module_type == "module_management" else module_type
    module = CaseModule(
        case_id=case.id,
        module_type=normalized_type,
        title=title or labels.get(normalized_type, normalized_type),
        status="draft",
        config_json={},
        result_json={},
    )
    db.add(module)
    db.flush()
    return {
        "module_id": module.id,
        "module_type": module.module_type,
        "title": module.title,
        "status": module.status,
    }


def list_component_items_payload(case: ExperimentCase, db: Session | None = None) -> dict[str, Any]:
    items = case.component_items
    if db is not None:
        items = db.query(CaseComponentItem).filter(CaseComponentItem.case_id == case.id).order_by(CaseComponentItem.category, CaseComponentItem.name).all()
    return {
        "items": [
            {
                "id": item.id,
                "module_id": item.module_id,
                "category": item.category,
                "name": item.name,
                "specification": item.specification,
                "quantity": item.quantity,
                "unit": item.unit,
                "owned": item.owned,
                "procurement_status": item.procurement_status,
            }
            for item in items
        ]
    }


def generate_component_items_payload(db: Session, case: ExperimentCase, module_id: int | None = None) -> dict[str, Any]:
    existing = db.query(CaseComponentItem).filter(CaseComponentItem.case_id == case.id)
    if module_id is not None:
        existing = existing.filter(CaseComponentItem.module_id == module_id)
    if existing.count() == 0:
        defaults = [
            ("instrument", "Laser safety eyewear", "OD and wavelength must match the setup", "Required PPE"),
            ("instrument", "Power meter", "Sensor head and range suitable for expected output", "Measure output power"),
            ("instrument", "BeamGage camera or beam profiler", "Compatible wavelength, attenuation, and pixel scale", "Measure beam profile"),
            ("optic", "Beam dumps", "Rated for wavelength and power", "Terminate beams"),
            ("optic", "Input mirror", "Coating and ROC from plan", "Cavity input optic"),
            ("optic", "Output coupler", "Transmission from plan", "Cavity output optic"),
            ("crystal", "Gain medium", "Material, doping, dimensions TBD", "Laser gain"),
            ("mount", "Kinematic mirror mounts", "Stable and compatible with optic diameter", "Alignment"),
        ]
        for category, name, specification, purpose in defaults:
            db.add(
                CaseComponentItem(
                    case_id=case.id,
                    module_id=module_id,
                    category=category,
                    name=name,
                    specification=specification,
                    quantity=1,
                    unit="pcs",
                    purpose=purpose,
                    required=True,
                    owned=False,
                    procurement_status="needed",
                    source="agent_generated",
                )
            )
        db.flush()
    return list_component_items_payload(case, db)


def save_generated_content_payload(generated: GeneratedContent) -> dict[str, Any]:
    return {"generated_content_id": generated.id, "content_type": generated.content_type}
