import uuid

from app.models import EvidenceStatus
from app.schemas import SearchResult
from app.services.knowledge_ask import KnowledgeAskService, MISSING_ANSWER
from app.services.llm import DraftAnswer, EvidenceAssessment, RevisedAnswer, VerificationResult


def passage(content: str = "Customer data is encrypted at rest.") -> SearchResult:
    return SearchResult(chunk_id=uuid.uuid4(), document_id=uuid.uuid4(), filename="security.md", content=content, metadata={"page_number": 4}, similarity_score=0.91)


class Retrieval:
    def __init__(self, results: list[SearchResult]):
        self.results = results
        self.calls: list[tuple[str, uuid.UUID | None]] = []

    def search(self, _db, _workspace_id, query, _top_k, document_id=None):
        self.calls.append((query, document_id))
        return self.results


class LLM:
    def __init__(self, values):
        self.values = iter(values)
        self.calls = []

    def generate_structured(self, prompt, response_model):
        self.calls.append(response_model)
        return next(self.values)


def test_missing_evidence_abstains_without_llm_call():
    retrieval = Retrieval([])
    llm = LLM([])
    response = KnowledgeAskService(retrieval, llm, max_rounds=2).ask(None, uuid.uuid4(), "What is our retention policy?")
    assert response.evidence_status == EvidenceStatus.MISSING
    assert response.answer == MISSING_ANSWER
    assert response.citations == []
    assert llm.calls == []


def test_strong_answer_returns_verified_citation_and_respects_scope():
    item = passage()
    retrieval = Retrieval([item])
    llm = LLM([
        EvidenceAssessment(status=EvidenceStatus.STRONG, sufficient=True),
        DraftAnswer(answer="Customer data is encrypted at rest.", evidence_status=EvidenceStatus.STRONG, citation_chunk_ids=[str(item.chunk_id)]),
        VerificationResult(supported=True, evidence_status=EvidenceStatus.STRONG, usable_citation_ids=[str(item.chunk_id)]),
    ])
    scope = uuid.uuid4()
    class Db:
        def scalar(self, _statement):
            return object()

    response = KnowledgeAskService(retrieval, llm, max_rounds=2).ask(Db(), uuid.uuid4(), "How is data protected?", scope)
    assert response.answer.startswith("Customer data")
    assert response.evidence_status == EvidenceStatus.STRONG
    assert response.citations[0].document_id == item.document_id
    assert retrieval.calls == [("How is data protected?", scope)]


def test_unsupported_draft_is_revised_once_then_persisted_in_response():
    item = passage()
    retrieval = Retrieval([item])
    llm = LLM([
        EvidenceAssessment(status=EvidenceStatus.STRONG, sufficient=True),
        DraftAnswer(answer="Unsupported claim.", evidence_status=EvidenceStatus.STRONG, citation_chunk_ids=[str(item.chunk_id)]),
        VerificationResult(supported=False, evidence_status=EvidenceStatus.MISSING, unsupported_claims=["Unsupported claim"]),
        RevisedAnswer(answer="Customer data is encrypted at rest.", evidence_status=EvidenceStatus.STRONG, citation_chunk_ids=[str(item.chunk_id)]),
        VerificationResult(supported=True, evidence_status=EvidenceStatus.STRONG, usable_citation_ids=[str(item.chunk_id)]),
    ])
    response = KnowledgeAskService(retrieval, llm, max_rounds=2).ask(None, uuid.uuid4(), "How is data protected?")
    assert response.answer == "Customer data is encrypted at rest."
    assert len(response.citations) == 1


def test_research_rounds_are_bounded_and_missing_when_assessment_stays_insufficient():
    retrieval = Retrieval([passage()])
    llm = LLM([
        EvidenceAssessment(status=EvidenceStatus.PARTIAL, sufficient=False, suggested_search_query="encryption details"),
        EvidenceAssessment(status=EvidenceStatus.PARTIAL, sufficient=False, suggested_search_query="one more query"),
    ])
    response = KnowledgeAskService(retrieval, llm, max_rounds=2).ask(None, uuid.uuid4(), "How is data protected?")
    assert response.evidence_status == EvidenceStatus.MISSING
    assert len(retrieval.calls) == 2
    assert len(llm.calls) == 2
