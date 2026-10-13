import asyncio
import json
import mimetypes
import logging
import tempfile
import uuid
from datetime import date
from pathlib import Path

from fastapi import Depends, FastAPI, File, Form, HTTPException, Query, Request, UploadFile, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse, Response, StreamingResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import Settings, get_settings
from app.database import SessionLocal, engine, get_db
from app.models import AgentRun, AgentRunStatus, AnswerOrigin, AnswerVersion, Citation, Document, DocumentChunk, DocumentStatus, EvidenceStatus, IngestionRun, IngestionRunStatus, Question, Questionnaire, QuestionnaireStatus, QuestionWorkflowStatus, User, Workspace
from app.schemas import AgentRunRead, AnswerCreate, AnswerVersionRead, ChunkRead, CitationCreate, CitationRead, DocumentRead, DocumentUpdate, DocumentUploadAccepted, GenerateRequest, IngestionRunRead, KnowledgeAskRead, KnowledgeAskRequest, NotApplicableRequest, PageRead, QuestionRead, QuestionnaireCreate, QuestionnairePreview, QuestionnaireRead, SearchRequest, SearchResult, WorkspaceCreate, WorkspaceRead
from app.services.embeddings import EmbeddingError, GeminiEmbeddingService
from app.services.ingestion import remove_from_knowledge
from app.services.retrieval import RetrievalService
from app.services.knowledge_ask import KnowledgeAskService, KnowledgeScopeError
from app.services.llm import GeminiLLMProvider
from app.services.storage import LocalFileStorage
from app.services.questionnaire_import import QuestionnairePreviewStore, inspect_questionnaire, read_rows
from app.services.review import approve, cancel_active_agent_runs, cancel_queued_agent_runs, create_version, not_applicable, reject
from app.services.export import export_csv
from app.services.queue import AgentQueue, IngestionQueue
from app.telemetry import configure_telemetry, current_trace_id, span
from sqlalchemy.exc import IntegrityError

app = FastAPI(title="AnswerForge API", version="0.1.0")
settings = get_settings()
configure_telemetry(settings, app=app, engine=engine)
logger = logging.getLogger(__name__)
app.add_middleware(CORSMiddleware, allow_origins=settings.cors_origins.split(","), allow_credentials=False, allow_methods=["*"], allow_headers=["*"])

SUPPORTED_TYPES = {".pdf": "application/pdf", ".txt": "text/plain", ".md": "text/markdown"}


def get_storage() -> LocalFileStorage:
    return LocalFileStorage(get_settings().storage_path)


def get_questionnaire_previews() -> QuestionnairePreviewStore:
    return QuestionnairePreviewStore(get_settings().storage_path)


def get_agent_queue() -> AgentQueue:
    return AgentQueue(get_settings())


def get_ingestion_queue() -> IngestionQueue:
    return IngestionQueue(get_settings())


def get_embeddings() -> GeminiEmbeddingService:
    try:
        config = get_settings()
        return GeminiEmbeddingService(config.gemini_api_key or config.embedding_api_key, config.embedding_model, config.embedding_dimensions)
    except EmbeddingError as error:
        raise HTTPException(status_code=503, detail=str(error)) from error


def get_llm() -> GeminiLLMProvider:
    try:
        config = get_settings()
        return GeminiLLMProvider(config.generation_api_key, config.llm_model)
    except RuntimeError as error:
        raise HTTPException(status_code=503, detail=str(error)) from error


def get_workspace_or_404(db: Session, workspace_id: uuid.UUID) -> Workspace:
    workspace = db.get(Workspace, workspace_id)
    if not workspace:
        raise HTTPException(status_code=404, detail="Workspace not found.")
    return workspace


def get_document_or_404(db: Session, document_id: uuid.UUID) -> Document:
    document = db.get(Document, document_id)
    if not document:
        raise HTTPException(status_code=404, detail="Document not found.")
    return document


def get_questionnaire_or_404(db: Session, questionnaire_id: uuid.UUID) -> Questionnaire:
    questionnaire = db.get(Questionnaire, questionnaire_id)
    if not questionnaire:
        raise HTTPException(status_code=404, detail="Questionnaire not found.")
    return questionnaire


def get_demo_user(db: Session) -> User:
    user = db.scalar(select(User).order_by(User.name).limit(1))
    if user:
        return user
    user = User(name="Demo User")
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/workspaces", response_model=WorkspaceRead, status_code=status.HTTP_201_CREATED)
def create_workspace(payload: WorkspaceCreate, db: Session = Depends(get_db)) -> Workspace:
    workspace = Workspace(name=payload.name.strip(), created_by=get_demo_user(db))
    db.add(workspace)
    db.commit()
    db.refresh(workspace)
    return workspace


@app.get("/workspaces", response_model=list[WorkspaceRead])
def list_workspaces(db: Session = Depends(get_db)) -> list[Workspace]:
    return list(db.scalars(select(Workspace).order_by(Workspace.created_at.desc())))


@app.post("/workspaces/{workspace_id}/questionnaires/preview", response_model=QuestionnairePreview)
async def preview_questionnaire(workspace_id: uuid.UUID, file: UploadFile = File(...), previews: QuestionnairePreviewStore = Depends(get_questionnaire_previews), db: Session = Depends(get_db)) -> dict:
    get_workspace_or_404(db, workspace_id)
    filename = Path(file.filename or "").name
    if Path(filename).suffix.lower() not in {".csv", ".xlsx"}:
        raise HTTPException(status_code=415, detail="Only CSV and XLSX questionnaires are supported.")
    data = await file.read()
    if not data:
        raise HTTPException(status_code=400, detail="The uploaded questionnaire is empty.")
    token = previews.save(filename, data)
    try:
        return inspect_questionnaire(previews.find(token), token)
    except Exception:
        previews.remove(token)
        raise


@app.post("/workspaces/{workspace_id}/questionnaires", response_model=QuestionnaireRead, status_code=status.HTTP_201_CREATED)
def create_questionnaire(workspace_id: uuid.UUID, payload: QuestionnaireCreate, previews: QuestionnairePreviewStore = Depends(get_questionnaire_previews), storage: LocalFileStorage = Depends(get_storage), db: Session = Depends(get_db)) -> Questionnaire:
    get_workspace_or_404(db, workspace_id)
    preview_path = previews.find(payload.preview_token)
    columns, rows = read_rows(preview_path)
    if payload.question_column not in columns or payload.answer_column not in columns or payload.question_column == payload.answer_column:
        raise HTTPException(status_code=422, detail="Choose distinct existing question and answer columns.")
    usable_rows = [(row_number, row) for row_number, row in rows if row.get(payload.question_column, "").strip()]
    if not usable_rows:
        raise HTTPException(status_code=422, detail="The selected question column has no questions.")
    original_filename = preview_path.name.removeprefix(f"{payload.preview_token}-")
    source_path = storage.save_questionnaire(workspace_id, original_filename, preview_path)
    questionnaire = Questionnaire(workspace_id=workspace_id, title=payload.title.strip(), status=QuestionnaireStatus.READY, question_column=payload.question_column, answer_column=payload.answer_column, context=payload.context.strip() if payload.context else None, storage_path=source_path, original_filename=original_filename, source_format=preview_path.suffix.lower().lstrip("."))
    db.add(questionnaire); db.flush()
    user = get_demo_user(db)
    for position, (row_number, row) in enumerate(usable_rows, start=1):
        question = Question(questionnaire_id=questionnaire.id, question_text=row[payload.question_column].strip(), workflow_status=QuestionWorkflowStatus.EXTRACTED, position=position, original_row=row_number, source_row=row)
        db.add(question); db.flush()
        answer = row.get(payload.answer_column, "").strip()
        if answer:
            version = AnswerVersion(question_id=question.id, version_number=1, answer_text=answer, evidence_status=EvidenceStatus.MISSING, origin=AnswerOrigin.IMPORTED, created_by_id=user.id)
            db.add(version); db.flush(); question.current_answer_version_id = version.id; question.workflow_status = QuestionWorkflowStatus.READY_FOR_REVIEW
    db.commit(); db.refresh(questionnaire); previews.remove(payload.preview_token)
    return questionnaire


@app.get("/workspaces/{workspace_id}/questionnaires", response_model=list[QuestionnaireRead])
def list_questionnaires(workspace_id: uuid.UUID, db: Session = Depends(get_db)) -> list[Questionnaire]:
    get_workspace_or_404(db, workspace_id)
    return list(db.scalars(select(Questionnaire).where(Questionnaire.workspace_id == workspace_id).order_by(Questionnaire.created_at.desc())))


@app.get("/questionnaires/{questionnaire_id}", response_model=QuestionnaireRead)
def get_questionnaire(questionnaire_id: uuid.UUID, db: Session = Depends(get_db)) -> Questionnaire:
    return get_questionnaire_or_404(db, questionnaire_id)


@app.delete("/questionnaires/{questionnaire_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_questionnaire(questionnaire_id: uuid.UUID, storage: LocalFileStorage = Depends(get_storage), db: Session = Depends(get_db)) -> None:
    questionnaire = get_questionnaire_or_404(db, questionnaire_id)
    storage_path = questionnaire.storage_path
    db.delete(questionnaire)
    db.commit()
    storage.delete(storage_path)


@app.get("/questionnaires/{questionnaire_id}/questions", response_model=list[QuestionRead])
def list_questions(questionnaire_id: uuid.UUID, workflow_status: QuestionWorkflowStatus | None = None, db: Session = Depends(get_db)) -> list[Question]:
    get_questionnaire_or_404(db, questionnaire_id)
    query = select(Question).where(Question.questionnaire_id == questionnaire_id).order_by(Question.position)
    if workflow_status: query = query.where(Question.workflow_status == workflow_status)
    return list(db.scalars(query))


@app.post("/questions/{question_id}/answers", response_model=AnswerVersionRead, status_code=status.HTTP_201_CREATED)
def write_answer(question_id: uuid.UUID, payload: AnswerCreate, db: Session = Depends(get_db)) -> AnswerVersion:
    question = db.get(Question, question_id)
    if not question: raise HTTPException(status_code=404, detail="Question not found.")
    cancel_active_agent_runs(db, question)
    version = create_version(db, question, payload.answer_text, EvidenceStatus.MISSING, AnswerOrigin.MANUAL if not question.current_answer_version_id else AnswerOrigin.EDITED, get_demo_user(db).id)
    db.commit(); db.refresh(version); return version


@app.post("/questions/{question_id}/approve", response_model=QuestionRead)
def approve_question(question_id: uuid.UUID, db: Session = Depends(get_db)) -> Question:
    question = db.get(Question, question_id)
    if not question: raise HTTPException(status_code=404, detail="Question not found.")
    approve(db, question); db.commit(); db.refresh(question); return question


@app.post("/questions/{question_id}/reject", response_model=QuestionRead)
def reject_question(question_id: uuid.UUID, db: Session = Depends(get_db)) -> Question:
    question = db.get(Question, question_id)
    if not question: raise HTTPException(status_code=404, detail="Question not found.")
    reject(question); db.commit(); db.refresh(question); return question


@app.post("/questions/{question_id}/not-applicable", response_model=QuestionRead)
def mark_not_applicable(question_id: uuid.UUID, payload: NotApplicableRequest, db: Session = Depends(get_db)) -> Question:
    question = db.get(Question, question_id)
    if not question: raise HTTPException(status_code=404, detail="Question not found.")
    not_applicable(question, payload.reason); db.commit(); db.refresh(question); return question


@app.get("/questions/{question_id}/answers", response_model=list[AnswerVersionRead])
def list_answer_versions(question_id: uuid.UUID, db: Session = Depends(get_db)) -> list[AnswerVersion]:
    if not db.get(Question, question_id): raise HTTPException(status_code=404, detail="Question not found.")
    return list(db.scalars(select(AnswerVersion).where(AnswerVersion.question_id == question_id).order_by(AnswerVersion.version_number.desc())))


@app.get("/answer-versions/{version_id}", response_model=AnswerVersionRead)
def get_answer_version(version_id: uuid.UUID, db: Session = Depends(get_db)) -> AnswerVersion:
    version = db.get(AnswerVersion, version_id)
    if not version: raise HTTPException(status_code=404, detail="Answer version not found.")
    return version


@app.post("/answer-versions/{version_id}/citations", response_model=CitationRead, status_code=status.HTTP_201_CREATED)
def attach_citation(version_id: uuid.UUID, payload: CitationCreate, db: Session = Depends(get_db)) -> Citation:
    version = db.get(AnswerVersion, version_id); chunk = db.get(DocumentChunk, payload.document_chunk_id)
    if not version: raise HTTPException(status_code=404, detail="Answer version not found.")
    if not chunk or chunk.document.is_deleted or chunk.document.workspace_id != version.question.questionnaire.workspace_id:
        raise HTTPException(status_code=422, detail="Evidence must be an active knowledge chunk in the questionnaire workspace.")
    citation = Citation(answer_version_id=version.id, document_id=chunk.document_id, document_chunk_id=chunk.id, quoted_text=chunk.content, page_number=chunk.chunk_metadata.get("page_number"), section_title=chunk.chunk_metadata.get("section_title"))
    db.add(citation)
    if version.evidence_status == EvidenceStatus.MISSING:
        version.evidence_status = EvidenceStatus.PARTIAL
    db.commit(); db.refresh(citation); return citation


@app.delete("/citations/{citation_id}", status_code=status.HTTP_204_NO_CONTENT)
def remove_citation(citation_id: uuid.UUID, db: Session = Depends(get_db)) -> None:
    citation = db.get(Citation, citation_id)
    if not citation: raise HTTPException(status_code=404, detail="Citation not found.")
    db.delete(citation); db.commit()


@app.get("/answer-versions/{version_id}/citations", response_model=list[CitationRead])
def list_citations(version_id: uuid.UUID, db: Session = Depends(get_db)) -> list[Citation]:
    if not db.get(AnswerVersion, version_id):
        raise HTTPException(status_code=404, detail="Answer version not found.")
    return list(db.scalars(select(Citation).where(Citation.answer_version_id == version_id).order_by(Citation.created_at)))


@app.get("/questionnaires/{questionnaire_id}/export")
def export_questionnaire(questionnaire_id: uuid.UUID, format: str = "csv", db: Session = Depends(get_db)) -> Response:
    questionnaire = get_questionnaire_or_404(db, questionnaire_id)
    if format != "csv": raise HTTPException(status_code=422, detail="Only CSV export is available in Stage 2.")
    content = export_csv(questionnaire)
    filename = f"{Path(questionnaire.original_filename).stem}-responses.csv"
    return Response(content, media_type="text/csv", headers={"Content-Disposition": f'attachment; filename="{filename}"'})


def enqueue_generation(db: Session, question: Question, payload: GenerateRequest, queue: AgentQueue) -> AgentRun:
    existing = db.scalar(select(AgentRun).where(AgentRun.question_id == question.id, AgentRun.status.in_([AgentRunStatus.QUEUED, AgentRunStatus.RUNNING])))
    if existing:
        return existing
    run = AgentRun(question_id=question.id, status=AgentRunStatus.QUEUED, model_provider="gemini", model_name=get_settings().llm_model, feedback=payload.feedback, trace_id=current_trace_id())
    question.workflow_status = QuestionWorkflowStatus.QUEUED
    question.questionnaire.status = QuestionnaireStatus.IN_REVIEW
    question.questionnaire.completed_at = None
    db.add(run)
    try:
        db.commit(); db.refresh(run)
    except IntegrityError:
        db.rollback()
        return db.scalar(select(AgentRun).where(AgentRun.question_id == question.id, AgentRun.status.in_([AgentRunStatus.QUEUED, AgentRunStatus.RUNNING])))
    try:
        queue.enqueue(run.id)
    except Exception as error:
        logger.exception("agent_run_enqueue_failed", extra={"agent_run_id": str(run.id), "question_id": str(question.id), "error_type": type(error).__name__})
        run.status = AgentRunStatus.FAILED; run.error_type = type(error).__name__; run.error_message = "Could not enqueue agent work."; question.workflow_status = QuestionWorkflowStatus.READY_FOR_REVIEW if question.current_answer_version_id else QuestionWorkflowStatus.FAILED; db.commit()
        raise HTTPException(status_code=503, detail="Agent queue is unavailable. Check Redis and the worker.") from error
    return run


@app.post("/questions/{question_id}/generate", response_model=AgentRunRead, status_code=status.HTTP_202_ACCEPTED)
def generate_question(question_id: uuid.UUID, payload: GenerateRequest = GenerateRequest(), queue: AgentQueue = Depends(get_agent_queue), db: Session = Depends(get_db)) -> AgentRun:
    question = db.get(Question, question_id)
    if not question: raise HTTPException(status_code=404, detail="Question not found.")
    return enqueue_generation(db, question, payload, queue)


@app.post("/questions/{question_id}/regenerate", response_model=AgentRunRead, status_code=status.HTTP_202_ACCEPTED)
def regenerate_question(question_id: uuid.UUID, payload: GenerateRequest = GenerateRequest(), queue: AgentQueue = Depends(get_agent_queue), db: Session = Depends(get_db)) -> AgentRun:
    question = db.get(Question, question_id)
    if not question: raise HTTPException(status_code=404, detail="Question not found.")
    return enqueue_generation(db, question, payload, queue)


@app.post("/questions/{question_id}/agent-runs/retry", response_model=AgentRunRead, status_code=status.HTTP_202_ACCEPTED)
def retry_queued_question(question_id: uuid.UUID, payload: GenerateRequest = GenerateRequest(), queue: AgentQueue = Depends(get_agent_queue), db: Session = Depends(get_db)) -> AgentRun:
    question = db.get(Question, question_id)
    if not question:
        raise HTTPException(status_code=404, detail="Question not found.")
    queued_run_ids = {run.id for run in question.agent_runs if run.status == AgentRunStatus.QUEUED}
    if not queued_run_ids:
        raise HTTPException(status_code=409, detail="Only queued, unstarted answer runs can be retried.")
    queue.remove_runs(queued_run_ids)
    cancel_queued_agent_runs(question)
    db.commit()
    return enqueue_generation(db, question, payload, queue)


@app.post("/questionnaires/{questionnaire_id}/generate", response_model=list[AgentRunRead], status_code=status.HTTP_202_ACCEPTED)
def generate_questionnaire(questionnaire_id: uuid.UUID, payload: GenerateRequest = GenerateRequest(), queue: AgentQueue = Depends(get_agent_queue), db: Session = Depends(get_db)) -> list[AgentRun]:
    questionnaire = get_questionnaire_or_404(db, questionnaire_id)
    return [enqueue_generation(db, question, payload, queue) for question in questionnaire.questions if question.workflow_status not in {QuestionWorkflowStatus.APPROVED, QuestionWorkflowStatus.NOT_APPLICABLE}]


@app.get("/agent-runs/{run_id}", response_model=AgentRunRead)
def get_agent_run(run_id: uuid.UUID, db: Session = Depends(get_db)) -> AgentRun:
    run = db.get(AgentRun, run_id)
    if not run: raise HTTPException(status_code=404, detail="Agent run not found.")
    return run


@app.get("/questions/{question_id}/agent-runs", response_model=list[AgentRunRead])
def list_agent_runs(question_id: uuid.UUID, db: Session = Depends(get_db)) -> list[AgentRun]:
    if not db.get(Question, question_id): raise HTTPException(status_code=404, detail="Question not found.")
    return list(db.scalars(select(AgentRun).where(AgentRun.question_id == question_id).order_by(AgentRun.created_at.desc())))


def _run_payload(run: AgentRun) -> dict:
    return AgentRunRead.model_validate(run).model_dump(mode="json")


def _sse_runs(request: Request, question_id: uuid.UUID | None = None, questionnaire_id: uuid.UUID | None = None) -> StreamingResponse:
    async def events():
        last_snapshot = ""
        heartbeat_at = 0
        while not await request.is_disconnected():
            with SessionLocal() as stream_db:
                statement = select(AgentRun).order_by(AgentRun.updated_at, AgentRun.created_at)
                if question_id is not None:
                    statement = statement.where(AgentRun.question_id == question_id)
                if questionnaire_id is not None:
                    statement = statement.join(Question).where(Question.questionnaire_id == questionnaire_id)
                runs = list(stream_db.scalars(statement))
                payload = [_run_payload(run) for run in runs]
            snapshot = json.dumps(payload, separators=(",", ":"), sort_keys=True)
            if snapshot != last_snapshot:
                for run in payload:
                    event = "run.completed" if run["status"] == "SUCCEEDED" else "run.failed" if run["status"] == "FAILED" else "run.phase"
                    yield f"event: {event}\nid: {run['id']}:{run['updated_at']}\ndata: {json.dumps(run, separators=(',', ':'))}\n\n"
                last_snapshot = snapshot
            if heartbeat_at % 15 == 0:
                yield ": heartbeat\n\n"
            heartbeat_at += 1
            await asyncio.sleep(1)

    return StreamingResponse(events(), media_type="text/event-stream", headers={"Cache-Control": "no-cache, no-transform", "X-Accel-Buffering": "no"})


@app.get("/questions/{question_id}/events")
def stream_question_events(question_id: uuid.UUID, request: Request, db: Session = Depends(get_db)) -> StreamingResponse:
    if not db.get(Question, question_id):
        raise HTTPException(status_code=404, detail="Question not found.")
    return _sse_runs(request, question_id=question_id)


@app.get("/questionnaires/{questionnaire_id}/events")
def stream_questionnaire_events(questionnaire_id: uuid.UUID, request: Request, db: Session = Depends(get_db)) -> StreamingResponse:
    get_questionnaire_or_404(db, questionnaire_id)
    return _sse_runs(request, questionnaire_id=questionnaire_id)


@app.get("/workspaces/{workspace_id}", response_model=WorkspaceRead)
def get_workspace(workspace_id: uuid.UUID, db: Session = Depends(get_db)) -> Workspace:
    return get_workspace_or_404(db, workspace_id)


@app.post("/workspaces/{workspace_id}/documents", response_model=DocumentUploadAccepted, status_code=status.HTTP_202_ACCEPTED)
async def upload_document(workspace_id: uuid.UUID, file: UploadFile = File(...), notes: str | None = Form(default=None, max_length=5000), department: str | None = Form(default=None, max_length=100), document_type: str | None = Form(default=None, max_length=100), effective_date: date | None = Form(default=None), db: Session = Depends(get_db), storage: LocalFileStorage = Depends(get_storage), queue: IngestionQueue = Depends(get_ingestion_queue)) -> DocumentUploadAccepted:
    get_workspace_or_404(db, workspace_id)
    filename = Path(file.filename or "").name
    suffix = Path(filename).suffix.lower()
    mime_type = SUPPORTED_TYPES.get(suffix)
    if not mime_type:
        raise HTTPException(status_code=415, detail="Only PDF, TXT, and MD files are supported.")
    body = await file.read()
    if not body:
        raise HTTPException(status_code=400, detail="The uploaded file is empty.")
    max_bytes = get_settings().max_upload_size_mb * 1024 * 1024
    if len(body) > max_bytes:
        raise HTTPException(status_code=413, detail=f"File exceeds the {get_settings().max_upload_size_mb} MB upload limit.")

    temporary_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as temporary_file:
            temporary_file.write(body)
            temporary_path = Path(temporary_file.name)
        storage_path = storage.save(workspace_id, filename, temporary_path)
    finally:
        if temporary_path:
            temporary_path.unlink(missing_ok=True)

    document = Document(workspace_id=workspace_id, filename=filename, storage_path=storage_path, notes=notes.strip() or None if notes else None, department=department.strip() or None if department else None, document_type=document_type.strip() or None if document_type else None, effective_date=effective_date, document_metadata={"mime_type": mime_type, "size_bytes": len(body)})
    run = IngestionRun(document=document, status=IngestionRunStatus.QUEUED, trace_id=current_trace_id())
    db.add_all([document, run])
    db.commit()
    try:
        queue.enqueue(run.id)
    except Exception as error:
        run.status = IngestionRunStatus.FAILED
        run.error_type = type(error).__name__
        run.error_message = "Could not enqueue ingestion work."
        document.status = DocumentStatus.FAILED
        document.document_metadata = {**document.document_metadata, "processing_error": "Could not enqueue ingestion work."}
        db.commit()
        raise HTTPException(status_code=503, detail="Ingestion queue is unavailable. Check Redis and the worker.") from error
    db.refresh(document)
    db.refresh(run)
    return DocumentUploadAccepted(document=document, ingestion_run=run)


@app.get("/workspaces/{workspace_id}/documents", response_model=list[DocumentRead])
def list_documents(workspace_id: uuid.UUID, visibility: str = Query("active", pattern="^(active|removed|all)$"), db: Session = Depends(get_db)) -> list[Document]:
    get_workspace_or_404(db, workspace_id)
    query = select(Document).where(Document.workspace_id == workspace_id)
    if visibility == "active":
        query = query.where(Document.is_deleted.is_(False))
    elif visibility == "removed":
        query = query.where(Document.is_deleted.is_(True))
    return list(db.scalars(query.order_by(Document.created_at.desc())))


@app.post("/workspaces/{workspace_id}/documents/requeue")
def requeue_workspace_documents(workspace_id: uuid.UUID, db: Session = Depends(get_db), queue: IngestionQueue = Depends(get_ingestion_queue)) -> dict[str, int]:
    get_workspace_or_404(db, workspace_id)
    documents = list(db.scalars(select(Document).where(Document.workspace_id == workspace_id, Document.is_deleted.is_(False))))
    runs = list(db.scalars(select(IngestionRun).join(Document).where(Document.workspace_id == workspace_id).order_by(IngestionRun.created_at.desc())))
    latest: dict[uuid.UUID, IngestionRun] = {}
    for run in runs:
        latest.setdefault(run.document_id, run)
    replaceable = [document for document in documents if document.status != DocumentStatus.READY and latest.get(document.id) and latest[document.id].status in {IngestionRunStatus.QUEUED, IngestionRunStatus.FAILED}]
    queued_run_ids = {latest[document.id].id for document in replaceable if latest[document.id].status == IngestionRunStatus.QUEUED}
    queue.remove_runs(queued_run_ids)
    for document in replaceable:
        prior = latest[document.id]
        prior.status = IngestionRunStatus.CANCELLED
        db.add(IngestionRun(document_id=document.id, status=IngestionRunStatus.QUEUED, attempt=prior.attempt + 1, trace_id=current_trace_id()))
        document.status = DocumentStatus.UPLOADED
        document.document_metadata = {**document.document_metadata, "processing_error": None}
    db.commit()
    for document in replaceable:
        run = db.scalar(select(IngestionRun).where(IngestionRun.document_id == document.id, IngestionRun.status == IngestionRunStatus.QUEUED).order_by(IngestionRun.created_at.desc()))
        if run:
            try:
                queue.enqueue(run.id)
            except Exception:
                run.status = IngestionRunStatus.FAILED
                document.status = DocumentStatus.FAILED
    db.commit()
    return {"requeued": len(replaceable), "in_progress": sum(1 for document in documents if document.status == DocumentStatus.PROCESSING)}


@app.get("/workspaces/{workspace_id}/document-events")
def stream_document_events(workspace_id: uuid.UUID, request: Request, db: Session = Depends(get_db)) -> StreamingResponse:
    get_workspace_or_404(db, workspace_id)

    async def events():
        last_snapshot = ""
        heartbeat_at = 0
        while not await request.is_disconnected():
            with SessionLocal() as stream_db:
                runs = list(stream_db.scalars(select(IngestionRun).join(Document).where(Document.workspace_id == workspace_id).order_by(IngestionRun.updated_at, IngestionRun.created_at)))
                payload = [IngestionRunRead.model_validate(run).model_dump(mode="json") for run in runs]
            snapshot = json.dumps(payload, separators=(",", ":"), sort_keys=True)
            if snapshot != last_snapshot:
                for run in payload:
                    event = "document.ready" if run["status"] == "SUCCEEDED" else "document.failed" if run["status"] == "FAILED" else "document.phase"
                    yield f"event: {event}\nid: {run['id']}:{run['updated_at']}\ndata: {json.dumps(run, separators=(',', ':'))}\n\n"
                last_snapshot = snapshot
            if heartbeat_at % 15 == 0:
                yield ": heartbeat\n\n"
            heartbeat_at += 1
            await asyncio.sleep(1)

    return StreamingResponse(events(), media_type="text/event-stream", headers={"Cache-Control": "no-cache, no-transform", "X-Accel-Buffering": "no"})


@app.get("/documents/{document_id}", response_model=DocumentRead)
def get_document(document_id: uuid.UUID, db: Session = Depends(get_db)) -> Document:
    return get_document_or_404(db, document_id)


@app.patch("/documents/{document_id}", response_model=DocumentRead)
def update_document_notes(document_id: uuid.UUID, payload: DocumentUpdate, db: Session = Depends(get_db)) -> Document:
    document = get_document_or_404(db, document_id)
    document.notes = payload.notes
    db.commit()
    db.refresh(document)
    return document


@app.get("/documents/{document_id}/ingestion-runs", response_model=list[IngestionRunRead])
def list_ingestion_runs(document_id: uuid.UUID, db: Session = Depends(get_db)) -> list[IngestionRun]:
    get_document_or_404(db, document_id)
    return list(db.scalars(select(IngestionRun).where(IngestionRun.document_id == document_id).order_by(IngestionRun.created_at.desc())))


@app.post("/documents/{document_id}/ingestion-runs/retry", response_model=IngestionRunRead, status_code=status.HTTP_202_ACCEPTED)
def retry_ingestion(document_id: uuid.UUID, db: Session = Depends(get_db), queue: IngestionQueue = Depends(get_ingestion_queue)) -> IngestionRun:
    document = get_document_or_404(db, document_id)
    active = db.scalar(select(IngestionRun).where(IngestionRun.document_id == document_id, IngestionRun.status.in_([IngestionRunStatus.QUEUED, IngestionRunStatus.RUNNING])))
    if active:
        return active
    prior_attempt = db.scalar(select(IngestionRun.attempt).where(IngestionRun.document_id == document_id).order_by(IngestionRun.attempt.desc()).limit(1)) or 0
    run = IngestionRun(document_id=document_id, status=IngestionRunStatus.QUEUED, attempt=prior_attempt + 1, trace_id=current_trace_id())
    document.status = DocumentStatus.UPLOADED
    db.add(run)
    db.commit()
    try:
        queue.enqueue(run.id)
    except Exception as error:
        run.status = IngestionRunStatus.FAILED
        run.error_type = type(error).__name__
        run.error_message = "Could not enqueue ingestion work."
        document.status = DocumentStatus.FAILED
        db.commit()
        raise HTTPException(status_code=503, detail="Ingestion queue is unavailable. Check Redis and the worker.") from error
    db.refresh(run)
    return run


@app.get("/documents/{document_id}/content", response_model=list[PageRead])
def get_document_content(document_id: uuid.UUID, db: Session = Depends(get_db)) -> list:
    document = get_document_or_404(db, document_id)
    if document.is_deleted:
        raise HTTPException(status_code=404, detail="Extracted content is not part of active knowledge.")
    return sorted(document.pages, key=lambda page: page.page_number)


@app.get("/documents/{document_id}/chunks", response_model=list[ChunkRead])
def get_document_chunks(document_id: uuid.UUID, db: Session = Depends(get_db)) -> list:
    document = get_document_or_404(db, document_id)
    if document.is_deleted:
        return []
    return sorted(document.chunks, key=lambda chunk: chunk.chunk_index)


@app.get("/documents/{document_id}/original")
def open_original(document_id: uuid.UUID, db: Session = Depends(get_db), storage: LocalFileStorage = Depends(get_storage)) -> HTMLResponse:
    document = get_document_or_404(db, document_id)
    if not storage.exists(document.storage_path):
        raise HTTPException(status_code=404, detail="Original source file is unavailable.")
    return HTMLResponse(f"<title>Starting download…</title><p>Starting download…</p><iframe hidden src=\"/documents/{document_id}/original/download\"></iframe><script>window.setTimeout(() => window.close(), 500)</script>")


@app.get("/documents/{document_id}/original/download")
def download_original(document_id: uuid.UUID, db: Session = Depends(get_db), storage: LocalFileStorage = Depends(get_storage)) -> FileResponse:
    document = get_document_or_404(db, document_id)
    if not storage.exists(document.storage_path):
        raise HTTPException(status_code=404, detail="Original source file is unavailable.")
    return FileResponse(storage.get_path(document.storage_path), filename=document.filename, media_type=document.document_metadata.get("mime_type", mimetypes.guess_type(document.filename)[0]))


@app.post("/documents/{document_id}/remove", response_model=DocumentRead)
def remove_document(document_id: uuid.UUID, db: Session = Depends(get_db)) -> Document:
    return remove_from_knowledge(db, get_document_or_404(db, document_id))


@app.post("/workspaces/{workspace_id}/search", response_model=list[SearchResult])
def search_knowledge(workspace_id: uuid.UUID, payload: SearchRequest, db: Session = Depends(get_db), embeddings: GeminiEmbeddingService = Depends(get_embeddings)) -> list[SearchResult]:
    get_workspace_or_404(db, workspace_id)
    if payload.document_id is not None and not db.scalar(select(Document.id).where(Document.id == payload.document_id, Document.workspace_id == workspace_id, Document.is_deleted.is_(False))):
        raise HTTPException(status_code=422, detail="The selected document is not active in this workspace.")
    config = get_settings()
    with span("retrieval.search", {"workspace.id": str(workspace_id), "retrieval.top_k": payload.top_k}):
        return RetrievalService(embeddings, config.hybrid_retrieval_enabled, config.retrieval_candidate_multiplier, config.retrieval_candidate_minimum).search(db, workspace_id, payload.query, payload.top_k, document_id=payload.document_id, filters=payload.filters)


@app.post("/workspaces/{workspace_id}/knowledge/ask", response_model=KnowledgeAskRead)
def ask_knowledge(workspace_id: uuid.UUID, payload: KnowledgeAskRequest, db: Session = Depends(get_db), embeddings: GeminiEmbeddingService = Depends(get_embeddings), llm: GeminiLLMProvider = Depends(get_llm)) -> KnowledgeAskRead:
    get_workspace_or_404(db, workspace_id)
    try:
        config = get_settings()
        return KnowledgeAskService(RetrievalService(embeddings, config.hybrid_retrieval_enabled, config.retrieval_candidate_multiplier, config.retrieval_candidate_minimum), llm, config.max_retrieval_rounds, config.agent_retrieval_top_k).ask(db, workspace_id, payload.question.strip(), payload.document_id, payload.filters)
    except KnowledgeScopeError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    except Exception as error:
        logger.exception("knowledge_ask_failed", extra={"workspace_id": str(workspace_id), "error_type": type(error).__name__})
        raise HTTPException(status_code=502, detail="Knowledge provider failed to complete this request. Try again.") from error
