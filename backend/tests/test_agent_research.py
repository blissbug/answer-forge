import uuid

from app.models import EvidenceStatus
from app.schemas import SearchResult
from app.services.agent import AgentOrchestrator
from app.services.llm import EvidenceAssessment


class FakeRetrieval:
    def __init__(self, rounds: list[list[SearchResult]]) -> None:
        self.rounds = rounds
        self.calls: list[str] = []

    def search(self, _db: object, _workspace_id: uuid.UUID, query: str, _top_k: int) -> list[SearchResult]:
        self.calls.append(query)
        return self.rounds[min(len(self.calls) - 1, len(self.rounds) - 1)]


class FakeLLM:
    def __init__(self, assessments: list[EvidenceAssessment]) -> None:
        self.assessments = assessments
        self.calls = 0

    def generate_structured(self, _prompt: str, _response_model: type[EvidenceAssessment]) -> EvidenceAssessment:
        response = self.assessments[self.calls]
        self.calls += 1
        return response


def result(chunk_id: uuid.UUID) -> SearchResult:
    return SearchResult(chunk_id=chunk_id, document_id=uuid.uuid4(), filename="security.md", content="Customer databases use AES-256.", metadata={"page_number": 14}, similarity_score=0.9)


def test_research_is_bounded_and_deduplicates_chunks() -> None:
    first = uuid.uuid4()
    second = uuid.uuid4()
    retrieval = FakeRetrieval([[result(first)], [result(first), result(second)], [result(second)]])
    llm = FakeLLM([
        EvidenceAssessment(status=EvidenceStatus.PARTIAL, sufficient=False, suggested_search_query="encryption at rest"),
        EvidenceAssessment(status=EvidenceStatus.PARTIAL, sufficient=False, suggested_search_query="database encryption"),
        EvidenceAssessment(status=EvidenceStatus.PARTIAL, sufficient=False, suggested_search_query="one more search"),
    ])
    orchestrator = AgentOrchestrator(retrieval, llm, max_rounds=2, top_k=5)  # type: ignore[arg-type]

    passages, sufficient, trace = orchestrator.research(None, uuid.uuid4(), "How is customer data encrypted?", uuid.uuid4())  # type: ignore[arg-type]

    assert not sufficient
    assert [passage.chunk_id for passage in passages] == [first, second]
    assert retrieval.calls == ["How is customer data encrypted?", "encryption at rest"]
    assert len(trace) == 2


def test_research_returns_missing_without_calling_llm_when_no_passages() -> None:
    retrieval = FakeRetrieval([[]])
    llm = FakeLLM([])
    orchestrator = AgentOrchestrator(retrieval, llm, max_rounds=3, top_k=5)  # type: ignore[arg-type]

    passages, sufficient, trace = orchestrator.research(None, uuid.uuid4(), "Unknown question", uuid.uuid4())  # type: ignore[arg-type]

    assert passages == []
    assert not sufficient
    assert trace[0]["result_count"] == 0
    assert llm.calls == 0
