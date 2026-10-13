import uuid
from types import SimpleNamespace

from app.schemas import RetrievalFilters
from app.services.embeddings import EmbeddingError
from app.services.retrieval import RetrievalService


def row(index: int, distance: float = 0.1):
    chunk = SimpleNamespace(id=uuid.uuid4(), chunk_index=index, content=f"chunk {index}", chunk_metadata={})
    document = SimpleNamespace(id=uuid.uuid4(), filename="policy.md")
    return chunk, document, distance


def test_rrf_promotes_a_chunk_found_by_dense_and_lexical_search() -> None:
    dense_only = row(1)
    shared = row(2)
    lexical_only = row(3)
    service = RetrievalService(embeddings=object())  # type: ignore[arg-type]

    results = service._fuse([dense_only, shared], [shared, lexical_only], top_k=3)

    assert [result.chunk_id for result in results] == [shared[0].id, dense_only[0].id, lexical_only[0].id]


def test_search_falls_back_to_lexical_results_when_embeddings_are_unavailable() -> None:
    lexical = row(1)

    class UnavailableEmbeddings:
        def embed_query(self, _query: str) -> list[float]:
            raise EmbeddingError("quota exhausted")

    class Result:
        def all(self):
            return [lexical]

    class Database:
        def execute(self, _statement):
            return Result()

    service = RetrievalService(UnavailableEmbeddings())  # type: ignore[arg-type]
    service._lexical_statement = lambda *_args: object()  # type: ignore[method-assign]

    results = service.search(Database(), uuid.uuid4(), "pricing", 5)  # type: ignore[arg-type]

    assert [result.chunk_id for result in results] == [lexical[0].id]


def test_metadata_filter_rejects_reversed_dates() -> None:
    try:
        RetrievalFilters(effective_from="2026-02-01", effective_to="2026-01-01")
    except ValueError as error:
        assert "effective_from" in str(error)
    else:
        raise AssertionError("reversed metadata dates must fail validation")
