import uuid
import logging

from sqlalchemy import Select, func, select
from sqlalchemy.orm import Session

from app.models import Document, DocumentChunk
from app.schemas import RetrievalFilters, SearchResult
from app.services.embeddings import EmbeddingError, EmbeddingService


RRF_K = 60
logger = logging.getLogger("uvicorn.error")


class RetrievalService:
    def __init__(self, embeddings: EmbeddingService, hybrid_enabled: bool = True, candidate_multiplier: int = 5, candidate_minimum: int = 50) -> None:
        self.embeddings = embeddings
        self.hybrid_enabled = hybrid_enabled
        self.candidate_multiplier = candidate_multiplier
        self.candidate_minimum = candidate_minimum

    def search(self, db: Session, workspace_id: uuid.UUID, query: str, top_k: int, document_id: uuid.UUID | None = None, filters: RetrievalFilters | None = None) -> list[SearchResult]:
        candidate_limit = max(top_k * self.candidate_multiplier, self.candidate_minimum)
        try:
            vector = self.embeddings.embed_query(query)
            dense_rows = db.execute(self._dense_statement(vector, workspace_id, document_id, filters, candidate_limit)).all()
        except EmbeddingError as error:
            logger.warning("embedding_search_unavailable; falling back to lexical search: %s", error)
            dense_rows = []
        if not self.hybrid_enabled:
            return [self._result(chunk, document, float(distance)) for chunk, document, distance in dense_rows[:top_k]] if dense_rows else self._fuse([], db.execute(self._lexical_statement(query, workspace_id, document_id, filters, candidate_limit)).all(), top_k)
        lexical_rows = db.execute(self._lexical_statement(query, workspace_id, document_id, filters, candidate_limit)).all()
        return self._fuse(dense_rows, lexical_rows, top_k)

    def _scoped(self, statement: Select, workspace_id: uuid.UUID, document_id: uuid.UUID | None, filters: RetrievalFilters | None) -> Select:
        statement = statement.join(Document, Document.id == DocumentChunk.document_id).where(Document.workspace_id == workspace_id, Document.is_deleted.is_(False))
        if document_id is not None:
            statement = statement.where(Document.id == document_id)
        if filters is None:
            return statement
        if filters.source_types:
            statement = statement.where(Document.source_type.in_(filters.source_types))
        if filters.departments:
            statement = statement.where(Document.department.in_(filters.departments))
        if filters.document_types:
            statement = statement.where(Document.document_type.in_(filters.document_types))
        if filters.effective_from:
            statement = statement.where(Document.effective_date >= filters.effective_from)
        if filters.effective_to:
            statement = statement.where(Document.effective_date <= filters.effective_to)
        return statement

    def _dense_statement(self, vector: list[float], workspace_id: uuid.UUID, document_id: uuid.UUID | None, filters: RetrievalFilters | None, limit: int) -> Select:
        distance = DocumentChunk.embedding.cosine_distance(vector)
        statement = self._scoped(select(DocumentChunk, Document, distance.label("distance")), workspace_id, document_id, filters)
        return statement.order_by(distance).limit(limit)

    def _lexical_statement(self, query: str, workspace_id: uuid.UUID, document_id: uuid.UUID | None, filters: RetrievalFilters | None, limit: int) -> Select:
        text_vector = func.to_tsvector("english", DocumentChunk.content)
        text_query = func.websearch_to_tsquery("english", query)
        rank = func.ts_rank_cd(text_vector, text_query)
        statement = self._scoped(select(DocumentChunk, Document, rank.label("lexical_rank")), workspace_id, document_id, filters)
        return statement.where(text_vector.op("@@")(text_query)).order_by(rank.desc()).limit(limit)

    def _fuse(self, dense_rows: list[tuple], lexical_rows: list[tuple], top_k: int) -> list[SearchResult]:
        candidates: dict[uuid.UUID, dict] = {}
        for rank, (chunk, document, distance) in enumerate(dense_rows, start=1):
            candidates[chunk.id] = {"chunk": chunk, "document": document, "distance": float(distance), "score": 1 / (RRF_K + rank)}
        for rank, (chunk, document, _lexical_score) in enumerate(lexical_rows, start=1):
            candidate = candidates.setdefault(chunk.id, {"chunk": chunk, "document": document, "distance": None, "score": 0.0})
            candidate["score"] += 1 / (RRF_K + rank)
        ranked = sorted(candidates.values(), key=lambda candidate: (-candidate["score"], candidate["chunk"].chunk_index))
        return [self._result(candidate["chunk"], candidate["document"], candidate["distance"]) for candidate in ranked[:top_k]]

    @staticmethod
    def _result(chunk: DocumentChunk, document: Document, distance: float | None) -> SearchResult:
        similarity = 0.0 if distance is None else max(0.0, 1 - distance)
        return SearchResult(chunk_id=chunk.id, document_id=document.id, filename=document.filename, content=chunk.content, metadata=chunk.chunk_metadata, similarity_score=round(similarity, 4))
