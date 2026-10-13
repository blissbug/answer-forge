import uuid
from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.models import AgentRunPhase, AgentRunStatus, AnswerOrigin, DocumentStatus, EvidenceStatus, IngestionPhase, IngestionRunStatus, QuestionnaireStatus, QuestionWorkflowStatus


class WorkspaceCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)


class WorkspaceRead(BaseModel):
    id: uuid.UUID
    name: str
    created_at: datetime
    model_config = ConfigDict(from_attributes=True)


class DocumentRead(BaseModel):
    id: uuid.UUID
    workspace_id: uuid.UUID
    filename: str
    status: DocumentStatus
    notes: str | None
    source_type: str
    department: str | None
    document_type: str | None
    effective_date: date | None
    metadata: dict = Field(validation_alias="document_metadata", serialization_alias="metadata")
    is_deleted: bool
    deleted_at: datetime | None
    created_at: datetime
    updated_at: datetime
    model_config = ConfigDict(from_attributes=True, populate_by_name=True)


class DocumentUpdate(BaseModel):
    notes: str | None = Field(default=None, max_length=5000)


class RetrievalFilters(BaseModel):
    source_types: list[Literal["upload"]] = Field(default_factory=list, max_length=20)
    departments: list[str] = Field(default_factory=list, max_length=20)
    document_types: list[str] = Field(default_factory=list, max_length=20)
    effective_from: date | None = None
    effective_to: date | None = None

    @model_validator(mode="after")
    def dates_are_ordered(self) -> "RetrievalFilters":
        if self.effective_from and self.effective_to and self.effective_from > self.effective_to:
            raise ValueError("effective_from must not be after effective_to")
        return self


class PageRead(BaseModel):
    page_number: int
    content: str
    metadata: dict = Field(validation_alias="page_metadata", serialization_alias="metadata")
    model_config = ConfigDict(from_attributes=True, populate_by_name=True)


class ChunkRead(BaseModel):
    id: uuid.UUID
    chunk_index: int
    content: str
    metadata: dict = Field(validation_alias="chunk_metadata", serialization_alias="metadata")
    model_config = ConfigDict(from_attributes=True, populate_by_name=True)


class SearchRequest(BaseModel):
    query: str = Field(min_length=1, max_length=4000)
    top_k: int = Field(default=8, ge=1, le=25)
    document_id: uuid.UUID | None = None
    filters: RetrievalFilters = Field(default_factory=RetrievalFilters)


class SearchResult(BaseModel):
    chunk_id: uuid.UUID
    document_id: uuid.UUID
    filename: str
    content: str
    metadata: dict
    similarity_score: float


class KnowledgeAskRequest(BaseModel):
    question: str = Field(min_length=1, max_length=4000)
    document_id: uuid.UUID | None = None
    filters: RetrievalFilters = Field(default_factory=RetrievalFilters)


class KnowledgeCitationRead(BaseModel):
    document_id: uuid.UUID
    document_title: str
    page_number: int | None
    section_title: str | None
    quoted_text: str
    similarity_score: float | None = None


class KnowledgeAskRead(BaseModel):
    question: str
    answer: str
    evidence_status: EvidenceStatus
    citations: list[KnowledgeCitationRead]


class QuestionnairePreview(BaseModel):
    token: str
    filename: str
    columns: list[str]
    row_count: int
    sample_rows: list[dict[str, str]]


class QuestionnaireCreate(BaseModel):
    preview_token: str
    title: str = Field(min_length=1, max_length=512)
    question_column: str = Field(min_length=1, max_length=255)
    answer_column: str = Field(min_length=1, max_length=255)
    context: str | None = Field(default=None, max_length=5000)


class QuestionnaireRead(BaseModel):
    id: uuid.UUID
    workspace_id: uuid.UUID
    title: str
    status: QuestionnaireStatus
    question_column: str
    answer_column: str
    context: str | None
    original_filename: str
    created_at: datetime
    completed_at: datetime | None
    total_questions: int = 0
    approved_questions: int = 0
    rejected_questions: int = 0
    not_applicable_questions: int = 0
    needs_review_questions: int = 0
    model_config = ConfigDict(from_attributes=True)


class QuestionRead(BaseModel):
    id: uuid.UUID
    questionnaire_id: uuid.UUID
    question_text: str
    workflow_status: QuestionWorkflowStatus
    position: int
    original_row: int
    current_answer_version_id: uuid.UUID | None
    current_answer_evidence_status: EvidenceStatus | None
    not_applicable_reason: str | None
    model_config = ConfigDict(from_attributes=True)


class AnswerCreate(BaseModel):
    answer_text: str = Field(min_length=1, max_length=50000)
    evidence_status: EvidenceStatus = EvidenceStatus.MISSING


class AnswerVersionRead(BaseModel):
    id: uuid.UUID
    question_id: uuid.UUID
    version_number: int
    answer_text: str
    evidence_status: EvidenceStatus
    origin: AnswerOrigin
    created_at: datetime
    model_config = ConfigDict(from_attributes=True)


class NotApplicableRequest(BaseModel):
    reason: str | None = Field(default=None, max_length=5000)


class CitationCreate(BaseModel):
    document_chunk_id: uuid.UUID


class CitationRead(BaseModel):
    id: uuid.UUID
    document_id: uuid.UUID
    document_chunk_id: uuid.UUID | None
    quoted_text: str
    page_number: int | None
    section_title: str | None
    relevance_score: float | None
    created_at: datetime
    document_filename: str
    source_removed: bool
    model_config = ConfigDict(from_attributes=True)


class AgentRunRead(BaseModel):
    id: uuid.UUID
    question_id: uuid.UUID
    answer_version_id: uuid.UUID | None
    status: AgentRunStatus
    phase: AgentRunPhase
    progress_message: str | None
    trace_id: str | None
    model_provider: str | None
    model_name: str | None
    retrieval_rounds: int
    latency_ms: int | None
    error_type: str | None
    error_message: str | None
    trace_data: dict | None
    created_at: datetime
    updated_at: datetime
    completed_at: datetime | None
    model_config = ConfigDict(from_attributes=True)


class GenerateRequest(BaseModel):
    feedback: str | None = Field(default=None, max_length=5000)


class IngestionRunRead(BaseModel):
    id: uuid.UUID
    document_id: uuid.UUID
    status: IngestionRunStatus
    phase: IngestionPhase
    attempt: int
    processed_chunks: int
    total_chunks: int | None
    error_type: str | None
    error_message: str | None
    trace_id: str | None
    created_at: datetime
    updated_at: datetime
    completed_at: datetime | None
    model_config = ConfigDict(from_attributes=True)


class DocumentUploadAccepted(BaseModel):
    document: DocumentRead
    ingestion_run: IngestionRunRead
