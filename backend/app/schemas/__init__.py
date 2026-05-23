"""Pydantic request and response schemas."""
from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field


class ExperimentCaseBase(BaseModel):
    title: str = Field(..., min_length=1, max_length=255)
    description: Optional[str] = None
    cavity_type: str = Field(..., pattern="^(linear|ring|bow-tie|custom)$")
    goal: str = Field(..., min_length=1)
    parameters: Dict[str, Any] = Field(default_factory=dict)
    symptoms: List[str] = Field(default_factory=list)


class ExperimentCaseCreate(ExperimentCaseBase):
    pass


class ExperimentCaseUpdate(BaseModel):
    title: Optional[str] = Field(None, min_length=1, max_length=255)
    description: Optional[str] = None
    cavity_type: Optional[str] = Field(None, pattern="^(linear|ring|bow-tie|custom)$")
    goal: Optional[str] = Field(None, min_length=1)
    parameters: Optional[Dict[str, Any]] = None
    symptoms: Optional[List[str]] = None


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


class KnowledgeSourceResponse(BaseModel):
    id: int
    case_id: Optional[int] = None
    attachment_id: Optional[int] = None
    generated_content_id: Optional[int] = None
    source_type: str
    title: str
    uri: Optional[str] = None
    content_hash: Optional[str] = None
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
    results: List[KnowledgeSearchResult]


class AgentTaskCreate(BaseModel):
    case_id: Optional[int] = None
    goal: str = Field(..., min_length=1)
    mode: str = Field(default="troubleshooting", pattern="^(troubleshooting|plan|report|rezonator)$")
    require_citations: bool = True


class AgentChatRequest(BaseModel):
    session_id: Optional[int] = None
    message: str = Field(..., min_length=1)
    case_id: Optional[int] = None
    mode: str = Field(default="auto", pattern="^(auto|chat|troubleshooting|plan|report|rezonator)$")
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
