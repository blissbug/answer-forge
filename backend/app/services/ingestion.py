import logging
from datetime import datetime, timezone

from sqlalchemy import delete
from sqlalchemy.orm import Session

from app.config import Settings
from app.models import Document, DocumentChunk, DocumentPage, DocumentStatus, IngestionPhase, IngestionRun, IngestionRunStatus
from app.services.chunking import chunk_pages
from app.services.embeddings import EmbeddingService
from app.services.parsing import parse_document
from app.services.storage import FileStorage

logger = logging.getLogger("uvicorn.error")


class IngestionService:
    def __init__(self, storage: FileStorage, embeddings: EmbeddingService, settings: Settings) -> None:
        self.storage = storage
        self.embeddings = embeddings
        self.settings = settings

    def process(self, db: Session, document: Document, run: IngestionRun) -> Document:
        logger.info("document_ingestion_started document_id=%s filename=%s mime_type=%s size_bytes=%s", document.id, document.filename, document.document_metadata.get("mime_type"), document.document_metadata.get("size_bytes"))
        document.status = DocumentStatus.PROCESSING
        run.status = IngestionRunStatus.RUNNING
        run.phase = IngestionPhase.PARSING
        run.error_type = None
        run.error_message = None
        db.commit()
        pages = parse_document(self.storage.get_path(document.storage_path), document.document_metadata["mime_type"])
        run.phase = IngestionPhase.CHUNKING
        db.commit()
        drafts = chunk_pages(pages, self.settings.chunk_size, self.settings.chunk_overlap)
        if not drafts:
            raise ValueError("No chunks could be generated from the extracted text.")
        run.phase = IngestionPhase.EMBEDDING
        run.total_chunks = len(drafts)
        run.processed_chunks = 0
        db.commit()
        vectors: list[list[float]] = []
        for start in range(0, len(drafts), 100):
            batch = drafts[start:start + 100]
            batch_vectors = self.embeddings.embed_texts([draft.content for draft in batch])
            if len(batch_vectors) != len(batch):
                raise ValueError("Embedding provider returned an unexpected number of vectors.")
            vectors.extend(batch_vectors)
            run.processed_chunks = len(vectors)
            db.commit()
        run.phase = IngestionPhase.PERSISTING
        db.commit()
        db.execute(delete(DocumentChunk).where(DocumentChunk.document_id == document.id))
        db.execute(delete(DocumentPage).where(DocumentPage.document_id == document.id))
        db.add_all([DocumentPage(document_id=document.id, page_number=page.page_number, content=page.content, page_metadata=page.metadata) for page in pages])
        db.add_all([DocumentChunk(document_id=document.id, chunk_index=index, content=draft.content, embedding=vector, chunk_metadata=draft.metadata) for index, (draft, vector) in enumerate(zip(drafts, vectors))])
        document.document_metadata = {**document.document_metadata, "page_count": len(pages), "chunk_count": len(drafts), "parser": "pypdf" if document.document_metadata["mime_type"] == "application/pdf" else "text", "processing_error": None}
        document.status = DocumentStatus.READY
        run.status = IngestionRunStatus.SUCCEEDED
        run.phase = IngestionPhase.READY
        run.completed_at = datetime.now(timezone.utc)
        db.commit()
        db.refresh(document)
        logger.info("document_ingestion_ready document_id=%s pages=%s chunks=%s", document.id, len(pages), len(drafts))
        return document


def mark_ingestion_failed(db: Session, run: IngestionRun, message: str, terminal: bool) -> None:
    document = run.document
    run.error_type = "IngestionError"
    run.error_message = message[:1000]
    if terminal:
        run.status = IngestionRunStatus.FAILED
        run.phase = IngestionPhase.FAILED
        run.completed_at = datetime.now(timezone.utc)
        document.status = DocumentStatus.FAILED
        document.document_metadata = {**document.document_metadata, "processing_error": message}
    else:
        run.status = IngestionRunStatus.QUEUED
        run.phase = IngestionPhase.QUEUED
        run.attempt += 1
    db.commit()


def remove_from_knowledge(db: Session, document: Document) -> Document:
    if document.is_deleted:
        return document
    db.execute(delete(DocumentChunk).where(DocumentChunk.document_id == document.id))
    document.is_deleted = True
    document.deleted_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(document)
    return document
