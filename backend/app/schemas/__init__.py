"""Pydantic request and response schemas."""
from datetime import datetime
from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field


class ExperimentCaseBase(BaseModel):
    project_id: Optional[int] = None
    title: str = Field(..., min_length=1, max_length=255)
    description: Optional[str] = None
    cavity_type: str = Field(..., pattern="^(linear|ring|bow-tie|custom)$")
    goal: str = Field(..., min_length=1)
    status: str = Field(default="draft", pattern="^(draft|active|paused|completed|archived)$")
    visibility: str = Field(default="project", pattern="^(private|project|organization)$")
    schema_version: str = "case_v2"
    tags: List[str] = Field(default_factory=list)
    parameters: Dict[str, Any] = Field(default_factory=dict)
    symptoms: List[str] = Field(default_factory=list)
    measurements: Dict[str, Any] = Field(default_factory=dict)
    safety_notes: Optional[str] = None
    conclusions: Optional[str] = None
    owner_id: Optional[int] = None


class ExperimentCaseCreate(ExperimentCaseBase):
    pass


class ExperimentCaseUpdate(BaseModel):
    project_id: Optional[int] = None
    title: Optional[str] = Field(None, min_length=1, max_length=255)
    description: Optional[str] = None
    cavity_type: Optional[str] = Field(None, pattern="^(linear|ring|bow-tie|custom)$")
    goal: Optional[str] = Field(None, min_length=1)
    status: Optional[str] = Field(None, pattern="^(draft|active|paused|completed|archived)$")
    visibility: Optional[str] = Field(None, pattern="^(private|project|organization)$")
    schema_version: Optional[str] = None
    tags: Optional[List[str]] = None
    parameters: Optional[Dict[str, Any]] = None
    symptoms: Optional[List[str]] = None
    measurements: Optional[Dict[str, Any]] = None
    safety_notes: Optional[str] = None
    conclusions: Optional[str] = None
    owner_id: Optional[int] = None


class ExperimentCaseResponse(ExperimentCaseBase):
    id: int
    created_at: datetime
    updated_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)


class AttachmentResponse(BaseModel):
    id: int
    case_id: int
    filename: str
    file_type: Optional[str] = None
    content_hash: Optional[str] = None
    uploaded_at: datetime

    model_config = ConfigDict(from_attributes=True)


class Citation(BaseModel):
    source_id: int
    chunk_id: int
    title: str
    source_type: str
    score: float
    snippet: str


class GeneratedContentResponse(BaseModel):
    id: int
    case_id: int
    content_type: str
    content: Dict[str, Any]
    model: Optional[str] = None
    prompt_version: Optional[str] = None
    input_tokens: Optional[int] = None
    output_tokens: Optional[int] = None
    latency_ms: Optional[int] = None
    cost_estimate: Optional[str] = None
    generated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class GenerateRequest(BaseModel):
    use_rag: bool = True
    top_k: int = Field(default=5, ge=1, le=20)


class CaseModuleCreate(BaseModel):
    module_type: str = Field(..., pattern="^(stability|beam_profile|spectrum|components|cavity_design|phase_match|coating_tmm|component_match|power_curve)$")
    title: Optional[str] = None
    config_json: Dict[str, Any] = Field(default_factory=dict)


class CaseModuleUpdate(BaseModel):
    title: Optional[str] = Field(None, min_length=1, max_length=255)
    status: Optional[str] = Field(None, pattern="^(draft|ready|running|completed|failed)$")
    config_json: Optional[Dict[str, Any]] = None
    result_json: Optional[Dict[str, Any]] = None


class CaseModuleFileResponse(BaseModel):
    id: int
    module_id: int
    filename: str
    file_type: Optional[str] = None
    file_role: str = "input"
    content_hash: Optional[str] = None
    metadata_json: Dict[str, Any] = Field(default_factory=dict)
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class CaseModuleResponse(BaseModel):
    id: int
    case_id: int
    module_type: str
    title: str
    status: str
    config_json: Dict[str, Any] = Field(default_factory=dict)
    result_json: Dict[str, Any] = Field(default_factory=dict)
    created_at: datetime
    updated_at: Optional[datetime] = None
    files: List[CaseModuleFileResponse] = Field(default_factory=list)

    model_config = ConfigDict(from_attributes=True)


class ModuleRunRequest(BaseModel):
    config_json: Dict[str, Any] = Field(default_factory=dict)
    save_generated_content: bool = True


class CaseComponentItemBase(BaseModel):
    category: str = "component"
    name: str = Field(..., min_length=1, max_length=255)
    specification: Optional[str] = None
    quantity: float = 1
    unit: str = "pcs"
    purpose: Optional[str] = None
    required: bool = True
    owned: bool = False
    procurement_status: str = Field(default="needed", pattern="^(needed|owned|optional|pending|ordered|received)$")
    vendor: Optional[str] = None
    part_number: Optional[str] = None
    notes: Optional[str] = None
    source: str = "manual"


class CaseComponentItemCreate(CaseComponentItemBase):
    module_id: Optional[int] = None


class CaseComponentItemUpdate(BaseModel):
    category: Optional[str] = None
    name: Optional[str] = Field(None, min_length=1, max_length=255)
    specification: Optional[str] = None
    quantity: Optional[float] = None
    unit: Optional[str] = None
    purpose: Optional[str] = None
    required: Optional[bool] = None
    owned: Optional[bool] = None
    procurement_status: Optional[str] = Field(None, pattern="^(needed|owned|optional|pending|ordered|received)$")
    vendor: Optional[str] = None
    part_number: Optional[str] = None
    notes: Optional[str] = None


class CaseComponentItemResponse(CaseComponentItemBase):
    id: int
    case_id: int
    module_id: Optional[int] = None
    created_at: datetime
    updated_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)


class KnowledgeSourceResponse(BaseModel):
    id: int
    case_id: Optional[int] = None
    attachment_id: Optional[int] = None
    generated_content_id: Optional[int] = None
    source_type: str
    title: str
    uri: Optional[str] = None
    content_hash: Optional[str] = None
    governance_status: str = "draft"
    version: int = 1
    owner_id: Optional[int] = None
    reviewed_by_id: Optional[int] = None
    reviewed_at: Optional[datetime] = None
    metadata_json: Dict[str, Any] = Field(default_factory=dict)
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class KnowledgeSearchRequest(BaseModel):
    query: str = Field(..., min_length=1)
    case_id: Optional[int] = None
    source_type: Optional[str] = None
    top_k: int = Field(default=5, ge=1, le=20)
    task_id: Optional[int] = None


class KnowledgeSearchResult(BaseModel):
    source_id: int
    chunk_id: int
    title: str
    source_type: str
    scope: str = "global"  # "global" = lab constitution, "case" = case-specific attachment
    score: float
    rank: int
    snippet: str
    metadata_json: Dict[str, Any] = Field(default_factory=dict)


class KnowledgeSearchResponse(BaseModel):
    query: str
    retrieval_run_id: int
    confidence: str = "low"
    no_answer: bool = False
    max_score: float = 0.0
    message: Optional[str] = None
    results: List[KnowledgeSearchResult]


class AgentTaskCreate(BaseModel):
    case_id: Optional[int] = None
    goal: str = Field(..., min_length=1)
    mode: str = Field(default="troubleshooting", pattern="^(troubleshooting|plan|report|stability|beam_profile|spectrum|components|module_management|cavity_design|phase_match|coating_tmm|component_match|power_curve)$")
    require_citations: bool = True


class AgentChatRequest(BaseModel):
    session_id: Optional[int] = None
    message: str = Field(..., min_length=1)
    case_id: Optional[int] = None
    mode: str = Field(default="auto", pattern="^(auto|chat|troubleshooting|plan|report|stability|beam_profile|spectrum|components|module_management|cavity_design|phase_match|coating_tmm|component_match|power_curve)$")
    require_citations: bool = True


class AgentChatResponse(BaseModel):
    session_id: int
    message: str
    routed_mode: str
    task: Optional["AgentTaskResponse"] = None
    generated_content_id: Optional[int] = None
    citations: List[Citation] = Field(default_factory=list)


class AgentChatSessionCreate(BaseModel):
    case_id: Optional[int] = None
    title: Optional[str] = None


class AgentChatMessageResponse(BaseModel):
    id: int
    session_id: int
    role: str
    content: str
    metadata_json: Dict[str, Any] = Field(default_factory=dict)
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class AgentChatSessionResponse(BaseModel):
    id: int
    case_id: Optional[int] = None
    title: Optional[str] = None
    created_at: datetime
    updated_at: Optional[datetime] = None
    messages: List[AgentChatMessageResponse] = Field(default_factory=list)

    model_config = ConfigDict(from_attributes=True)


class AgentStepResponse(BaseModel):
    id: int
    task_id: int
    step_index: int
    title: str
    status: str
    rationale: Optional[str] = None
    result_summary: Optional[str] = None
    created_at: datetime
    updated_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)


class AgentToolCallResponse(BaseModel):
    id: int
    task_id: int
    step_id: Optional[int] = None
    tool_name: str
    input_json: Dict[str, Any] = Field(default_factory=dict)
    output_json: Dict[str, Any] = Field(default_factory=dict)
    status: str
    latency_ms: Optional[int] = None
    error_message: Optional[str] = None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class AgentTaskResponse(BaseModel):
    id: int
    case_id: Optional[int] = None
    user_id: Optional[int] = None
    goal: str
    mode: str
    status: str
    risk_level: str
    final_content_id: Optional[int] = None
    created_at: datetime
    updated_at: Optional[datetime] = None
    steps: List[AgentStepResponse] = Field(default_factory=list)
    tool_calls: List[AgentToolCallResponse] = Field(default_factory=list)

    model_config = ConfigDict(from_attributes=True)


class AuditLogResponse(BaseModel):
    id: int
    user_id: Optional[int] = None
    actor: str
    action: str
    resource_type: str
    resource_id: Optional[str] = None
    request_id: Optional[str] = None
    metadata_json: Dict[str, Any] = Field(default_factory=dict)
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class OrganizationCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)


class OrganizationResponse(OrganizationCreate):
    id: int
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class UserCreate(BaseModel):
    email: str = Field(..., min_length=3, max_length=255)
    display_name: str = Field(..., min_length=1, max_length=255)
    role: str = Field(default="user", pattern="^(user|reviewer|admin)$")
    organization_id: Optional[int] = None


class UserResponse(UserCreate):
    id: int
    is_active: bool = True
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class GroupCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    description: Optional[str] = None
    organization_id: Optional[int] = None


class GroupResponse(GroupCreate):
    id: int
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class MembershipCreate(BaseModel):
    user_id: Optional[int] = None
    group_id: Optional[int] = None
    role: str = Field(default="viewer", pattern="^(viewer|editor|owner|member)$")


class ProjectCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    description: Optional[str] = None
    organization_id: Optional[int] = None
    visibility: str = Field(default="private", pattern="^(private|organization)$")


class ProjectResponse(ProjectCreate):
    id: int
    created_at: datetime
    updated_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)


class KnowledgeGovernanceUpdate(BaseModel):
    governance_status: str = Field(..., pattern="^(draft|approved|deprecated|archived)$")
    reviewer_id: Optional[int] = None
    note: Optional[str] = None


class PromptVersionCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    version: str = Field(..., min_length=1, max_length=50)
    content: str = Field(..., min_length=1)
    metadata_json: Dict[str, Any] = Field(default_factory=dict)
    is_active: bool = False
    created_by_id: Optional[int] = None


class PromptVersionResponse(PromptVersionCreate):
    id: int
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class WorkflowVersionCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    version: str = Field(..., min_length=1, max_length=50)
    definition: Dict[str, Any]
    metadata_json: Dict[str, Any] = Field(default_factory=dict)
    is_active: bool = False
    created_by_id: Optional[int] = None


class WorkflowVersionResponse(WorkflowVersionCreate):
    id: int
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class RagEvalItem(BaseModel):
    id: Optional[str] = None
    query: str = Field(..., min_length=1)
    expected_source_ids: List[int] = Field(default_factory=list)
    expected_source_title_contains: Optional[str] = None
    expected_terms: List[str] = Field(default_factory=list)
    case_id: Optional[int] = None
    should_answer: bool = True


class RagEvalRequest(BaseModel):
    name: str = Field(default="ad hoc rag eval", min_length=1, max_length=255)
    top_k: int = Field(default=5, ge=1, le=20)
    dataset: List[RagEvalItem] = Field(..., min_length=1)


class RagEvalRunResponse(BaseModel):
    id: int
    name: str
    dataset: List[Dict[str, Any]]
    results: Any
    total_questions: int
    hit_rate: float
    mean_max_score: float
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


# --- Structured optics inventory (L0) + component matching (L1) -------------

class CoatingSpecResponse(BaseModel):
    id: int
    surface: str
    wl_min_nm: float
    wl_max_nm: float
    function: str
    value_type: Optional[str] = None
    comparator: Optional[str] = None
    value_pct: Optional[float] = None
    raw_fragment: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)


class InventoryItemResponse(BaseModel):
    id: int
    category: str
    name: str
    diameter_mm: Optional[float] = None
    roc_mm: Optional[float] = None
    roc_is_flat: Optional[bool] = None
    thickness_mm: Optional[float] = None
    dimensions: Optional[str] = None
    cut_angle_theta_deg: Optional[float] = None
    cut_angle_phi_deg: Optional[float] = None
    cut_axis: Optional[str] = None
    doping_pct: Optional[float] = None
    material: Optional[str] = None
    quantity: Optional[float] = None
    location: Optional[str] = None
    keeper: Optional[str] = None
    vendor: Optional[str] = None
    raw_spec: Optional[str] = None
    parse_confidence: Optional[str] = None
    parse_notes: Optional[List[str]] = None
    condition: Optional[str] = None
    condition_manual: Optional[str] = None
    condition_note: Optional[str] = None
    condition_marked_by: Optional[str] = None
    # `condition` is what the workbook text implied; `effective_condition` is
    # what a human said if they said anything. Callers should read the latter.
    effective_condition: Optional[str] = None
    # Derived per request from open loans, never stored: `quantity` must keep
    # meaning "what the workbook says the lab owns", because the importer
    # overwrites it on every re-import.
    on_loan_qty: Optional[float] = None
    available_qty: Optional[float] = None
    coatings: List[CoatingSpecResponse] = Field(default_factory=list)

    model_config = ConfigDict(from_attributes=True)


class InventoryImportResponse(BaseModel):
    source_file: str
    total_rows: int
    imported: int
    needs_review: int
    partial: int
    skipped_empty: int
    coating_bands: int
    review_queue: List[Dict[str, Any]] = Field(default_factory=list)


class SurfaceRequirement(BaseModel):
    wavelength_nm: float = Field(..., gt=100, lt=5000)
    function: str = Field(..., pattern="^(?i)(HR|AR|HT|PR)$")
    min_R_pct: Optional[float] = Field(default=None, ge=0, le=100)


class InventoryBorrowRequest(BaseModel):
    # Required because local mode has no login: without a typed name, "who has
    # it" would be permanently blank, which is the one question this feature exists to answer.
    borrower_name: str = Field(min_length=1, max_length=255)
    quantity: float = Field(default=1, gt=0)
    purpose: Optional[str] = None
    expected_return_at: Optional[datetime] = None


class InventoryReturnRequest(BaseModel):
    note: Optional[str] = None
    # Returning it is when you discover it is chipped.
    condition_on_return: Optional[Literal["ok", "damaged", "uncertain"]] = None


class InventoryConditionRequest(BaseModel):
    # None clears the human verdict and falls back to the parsed condition.
    condition: Optional[Literal["ok", "damaged", "uncertain"]] = None
    note: Optional[str] = None


class ComponentMatchRequest(BaseModel):
    role: str = Field(default="component", max_length=120)
    category: Optional[str] = None
    surfaces: List[SurfaceRequirement] = Field(default_factory=list)
    roc_mm: Optional[Any] = None          # number or "flat"
    roc_tol_pct: float = Field(default=2.0, ge=0, le=50)
    min_diameter_mm: Optional[float] = Field(default=None, gt=0)
    quantity: float = Field(default=1, gt=0)
    max_results: int = Field(default=10, ge=1, le=50)
