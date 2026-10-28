from typing import Any, Literal

from pydantic import Field, model_validator

from .optics import StrictInput


class Question(StrictInput):
    question: str = Field(min_length=1)
    why: str = Field(min_length=1, description="Which decision or calculation this unlocks")
    how_to_obtain: str = Field(min_length=1, description="Practical measurement, label, datasheet, or observation to obtain the information")
    expected_format: str = Field(min_length=1, description="Units and an example reply")


class Fact(StrictInput):
    statement: str
    source: str = Field(description="User message, attachment id, inventory id, or actual tool call id; never fabricated")
    kind: Literal["user_stated", "document", "calculated", "hypothesis"]


class Finish(StrictInput):
    status: Literal["completed", "partial", "needs_input", "unsupported"]
    summary: str = Field(min_length=1, max_length=16000)
    findings: list[str] = Field(default_factory=list, max_length=30)
    facts: list[Fact] = Field(default_factory=list, max_length=50)
    assumptions: list[str] = Field(default_factory=list, max_length=30)
    questions: list[Question] = Field(default_factory=list, max_length=6)
    next_steps: list[str] = Field(default_factory=list, max_length=20)
    evidence_tool_call_ids: list[int] = Field(default_factory=list, description="Persisted call ids returned by executed tools, not model call ids")

    @model_validator(mode="after")
    def outcome(self):
        if self.status == "needs_input" and not self.questions:
            raise ValueError("needs_input requires an actionable question including how to obtain the missing information")
        if self.status == "completed" and self.questions:
            raise ValueError("Required unanswered questions mean partial or needs_input, not completed")
        if self.status == "unsupported" and not self.next_steps:
            raise ValueError("unsupported requires a concrete alternative or next step")
        return self


class InventoryQuery(StrictInput):
    query: str = ""
    category: str | None = None
    offset: int = Field(default=0, ge=0)
    limit: int = Field(default=40, ge=1, le=100)


class AttachmentQuery(StrictInput):
    attachment_id: int
    offset: int = Field(default=0, ge=0)
    limit: int = Field(default=12000, ge=100, le=20000)


class ArtifactQuery(StrictInput):
    content_id: int
    path: str = Field(default="", description="Optional dot-separated JSON key/index path within artifact content")


class ToolResultQuery(StrictInput):
    tool_call_id: int
    path: str = Field(default="", description="Optional dot-separated key/index path within saved tool output")


class HistoryQuery(StrictInput):
    before_id: int | None = None
    limit: int = Field(default=20, ge=1, le=50)


class KnowledgeQuery(StrictInput):
    query: str = Field(min_length=1)
    top_k: int = Field(default=5, ge=1, le=10)


class LiteratureQuery(StrictInput):
    query: str = Field(min_length=1)
    max_results: int = Field(default=8, ge=1, le=20)
    year_from: int | None = None
    sort: Literal["relevance", "citations", "year"] = "relevance"


class PowerCurve(StrictInput):
    pump_w: list[float] = Field(min_length=3, max_length=3000)
    output_w: list[float] = Field(min_length=3, max_length=3000)
    pump_basis: Literal["incident", "absorbed", "diode_nominal"]
    data_source: str = Field(min_length=1, description="Actual measurement source; synthetic data must be explicitly identified")


class CausticData(StrictInput):
    z_mm: list[float] = Field(min_length=5, max_length=3000)
    radius_mm: list[float] = Field(min_length=5, max_length=3000)
    wavelength_nm: float = Field(gt=0)
    data_source: str = Field(min_length=1)


class ImportDesignProject(StrictInput):
    content_id: int
    candidate: int = Field(default=1, ge=1, le=5)
    base_revision_id: int | None = None


class PhaseMatch(StrictInput):
    crystal: Literal["bbo", "lbo", "ktp", "bibo"]
    lambda1_nm: float = Field(gt=0)
    lambda2_nm: float | None = Field(default=None, gt=0)
    pm_type: Literal["I", "II"] = "I"


class ComponentMatch(StrictInput):
    requirement: dict[str, Any] = Field(description="Inventory evaluator requirement: category, quantity, roc_mm ('flat' or signed mm), roc_tol_pct, min_diameter_mm, surfaces=[{wavelength_nm:1064, function:'HR', min_R_pct:99.8}]. Unknown properties remain unverified, not automatically matched.")


class Coating(StrictInput):
    config: dict[str, Any] = Field(description="Coating evaluator config; use tool documentation via inspect_tool before configuring this tool.")


class LinearDesign(StrictInput):
    message: str = Field(description="Explicit user request for supported end-pumped plane-concave laser design; no invented user facts.")


class SavedAnalysis(StrictInput):
    content_id: int
    candidate: int = Field(default=1, ge=1, le=5)
    mode: Literal["cavity", "pump"] = "cavity"
    output_gap_mm: float | None = Field(default=None, ge=.001, le=2000)
    thermal_f_mm: float | None = Field(default=None, ge=1, le=1e7, description="Physical focal length inside crystal; general analyze_optical_system uses air-equivalent f=thermal_f_mm/n instead.")
    samples: int = Field(default=900, ge=100, le=5000)


class ToolHelp(StrictInput):
    name: str
