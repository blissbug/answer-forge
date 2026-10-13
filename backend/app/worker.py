import uuid

from rq import get_current_job

from app.config import get_settings
from app.database import SessionLocal
from app.main import get_demo_user
from app.models import IngestionRun
from app.services.agent import AgentOrchestrator
from app.services.embeddings import EmbeddingError, GeminiEmbeddingService
from app.services.ingestion import IngestionService, mark_ingestion_failed
from app.services.llm import GeminiLLMProvider
from app.services.retrieval import RetrievalService
from app.services.storage import LocalFileStorage
from app.telemetry import configure_telemetry, current_trace_id, extract_trace_context, span


def process_agent_run(run_id: str, trace_context: dict[str, str] | None = None) -> None:
    settings = get_settings()
    configure_telemetry(settings, service_name="answerforge-agent-worker")
    with SessionLocal() as db:
        with span("agent.job", {"agent_run.id": run_id}, extract_trace_context(trace_context)):
            orchestrator = AgentOrchestrator(RetrievalService(GeminiEmbeddingService(settings.gemini_api_key or settings.embedding_api_key, settings.embedding_model, settings.embedding_dimensions), settings.hybrid_retrieval_enabled, settings.retrieval_candidate_multiplier, settings.retrieval_candidate_minimum), GeminiLLMProvider(settings.generation_api_key, settings.llm_model), settings.max_retrieval_rounds, settings.agent_retrieval_top_k)
            run = orchestrator.process_run(db, uuid.UUID(run_id), get_demo_user(db).id)
            if run and not run.trace_id:
                run.trace_id = current_trace_id()
                db.commit()


def process_ingestion_run(run_id: str, trace_context: dict[str, str] | None = None) -> None:
    settings = get_settings()
    configure_telemetry(settings, service_name="answerforge-ingestion-worker")
    job = get_current_job()
    with SessionLocal() as db:
        run = db.get(IngestionRun, uuid.UUID(run_id))
        if run is None or run.status.value in {"SUCCEEDED", "FAILED", "CANCELLED"}:
            return
        try:
            with span("ingestion.job", {"ingestion_run.id": run_id}, extract_trace_context(trace_context)):
                if not run.trace_id:
                    run.trace_id = current_trace_id()
                    db.commit()
                IngestionService(LocalFileStorage(settings.storage_path), GeminiEmbeddingService(settings.gemini_api_key or settings.embedding_api_key, settings.embedding_model, settings.embedding_dimensions), settings).process(db, run.document, run)
        except Exception as error:
            db.rollback()
            run = db.get(IngestionRun, uuid.UUID(run_id))
            if run is None:
                raise
            retries_left = getattr(job, "retries_left", 0) if job else 0
            terminal = isinstance(error, EmbeddingError) or retries_left <= 0
            mark_ingestion_failed(db, run, str(error), terminal=terminal)
            if terminal:
                return
            raise
