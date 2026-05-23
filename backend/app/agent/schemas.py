"""Structured output schemas and validation for Agent-generated artifacts."""
from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field, model_validator


# ---------------------------------------------------------------------------
# Schema definitions
# ---------------------------------------------------------------------------

class ExperimentPlanSchema(BaseModel):
    objective: str = Field(default="", description="Experiment objective")
    setup: str = Field(default="", description="Equipment and optical setup description")
    steps: list[str] = Field(default_factory=list, description="Ordered experimental steps")
    measurements: list[str] = Field(default_factory=list, description="Measurements to record")
    risks: list[str] = Field(default_factory=list, description="Safety risks and mitigations")
    next_actions: list[str] = Field(default_factory=list, description="Follow-up actions")

    @model_validator(mode="after")
    def ensure_steps_not_empty(self) -> "ExperimentPlanSchema":
        if not self.steps:
            self.steps = ["[Step details not provided — please review and complete]"]
        return self


class TroubleshootingSchema(BaseModel):
    symptom: str = Field(default="", description="Observed symptom or problem")
    possible_causes: list[str] = Field(default_factory=list, description="Possible root causes")
    diagnostic_checks: list[str] = Field(default_factory=list, description="Checks to perform")
    recommended_actions: list[str] = Field(default_factory=list, description="Recommended fixes")
    expected_observations: list[str] = Field(default_factory=list, description="Expected results after fix")
    safety_notes: list[str] = Field(default_factory=list, description="Safety precautions")

    @model_validator(mode="after")
    def ensure_causes_not_empty(self) -> "TroubleshootingSchema":
        if not self.possible_causes:
            self.possible_causes = ["[Cause analysis not provided — please review]"]
        return self


class ExperimentReportSchema(BaseModel):
    title: str = Field(default="", description="Report title")
    background: str = Field(default="", description="Background and motivation")
    method: str = Field(default="", description="Experimental method")
    observations: str = Field(default="", description="Key observations")
    data_summary: str = Field(default="", description="Summary of collected data")
    conclusion: str = Field(default="", description="Conclusions drawn")
    next_steps: list[str] = Field(default_factory=list, description="Recommended next steps")

    @model_validator(mode="after")
    def ensure_title_not_empty(self) -> "ExperimentReportSchema":
        if not self.title:
            self.title = "[Report title not provided]"
        return self


class ResonatorDraftSchema(BaseModel):
    cavity_type: str = Field(default="", description="Cavity type (linear/ring/bow-tie)")
    components: list[str] = Field(default_factory=list, description="Optical components list")
    distances: dict[str, Any] = Field(default_factory=dict, description="Component distances (mm)")
    crystal_position: str = Field(default="", description="Crystal position description")
    parameters_to_scan: list[str] = Field(default_factory=list, description="Parameters to scan in simulation")
    simulation_notes: str = Field(default="", description="Notes for ReZonator simulation")

    @model_validator(mode="after")
    def ensure_cavity_type(self) -> "ResonatorDraftSchema":
        if not self.cavity_type:
            self.cavity_type = "linear"
        return self


# ---------------------------------------------------------------------------
# Schema registry
# ---------------------------------------------------------------------------
_SCHEMA_MAP: dict[str, type[BaseModel]] = {
    "plan": ExperimentPlanSchema,
    "troubleshooting": TroubleshootingSchema,
    "report": ExperimentReportSchema,
    "rezonator": ResonatorDraftSchema,
}

REQUIRED_FIELDS: dict[str, list[str]] = {
    "plan": ["objective", "setup", "steps", "measurements", "risks", "next_actions"],
    "troubleshooting": ["symptom", "possible_causes", "diagnostic_checks", "recommended_actions", "expected_observations", "safety_notes"],
    "report": ["title", "background", "method", "observations", "data_summary", "conclusion", "next_steps"],
    "rezonator": ["cavity_type", "components", "distances", "crystal_position", "parameters_to_scan", "simulation_notes"],
}


# ---------------------------------------------------------------------------
# Validation and repair
# ---------------------------------------------------------------------------

class ValidationResult:
    """Result of schema validation."""

    def __init__(self, content_type: str, raw: dict[str, Any], validated: dict[str, Any]):
        self.content_type = content_type
        self.raw = raw
        self.validated = validated
        required = REQUIRED_FIELDS.get(content_type, [])
        self.missing_fields = [f for f in required if not raw.get(f)]
        self.repaired_fields = [f for f in self.missing_fields if validated.get(f)]
        self.passed = len(self.missing_fields) == 0
        self.repaired = len(self.repaired_fields) > 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "content_type": self.content_type,
            "passed": self.passed,
            "repaired": self.repaired,
            "missing_fields": self.missing_fields,
            "repaired_fields": self.repaired_fields,
        }


def validate_and_repair(content_type: str, raw: dict[str, Any]) -> ValidationResult:
    """Validate a generated artifact against its schema and repair missing fields.

    Returns a ValidationResult with the validated (and repaired) content dict.
    The Pydantic model's @model_validator hooks handle the actual repair logic.
    """
    schema_cls = _SCHEMA_MAP.get(content_type)
    if schema_cls is None:
        # Unknown type — return as-is
        return ValidationResult(content_type, raw, raw)

    # Pydantic will fill defaults and run validators (repair hooks)
    try:
        obj = schema_cls.model_validate(raw)
        validated = obj.model_dump()
    except Exception:
        # If Pydantic fails entirely, fall back to raw with empty defaults
        obj = schema_cls()
        validated = obj.model_dump()

    return ValidationResult(content_type, raw, validated)


def validate_artifact(content_type: str, content: dict[str, Any]) -> dict[str, Any]:
    """Validate and repair an artifact in-place. Returns the repaired content dict."""
    result = validate_and_repair(content_type, content)
    return result.validated
