import json
from typing import Protocol, TypeVar

from google import genai
from google.genai import types
from pydantic import BaseModel

from app.models import EvidenceStatus

T = TypeVar("T", bound=BaseModel)


class EvidenceAssessment(BaseModel):
    status: EvidenceStatus
    sufficient: bool
    missing_information: list[str] = []
    conflicting_claims: list[str] = []
    suggested_search_query: str | None = None


class DraftAnswer(BaseModel):
    answer: str
    evidence_status: EvidenceStatus
    citation_chunk_ids: list[str]


class VerificationResult(BaseModel):
    supported: bool
    evidence_status: EvidenceStatus
    unsupported_claims: list[str] = []
    conflicts: list[str] = []
    usable_citation_ids: list[str] = []


class RevisedAnswer(BaseModel):
    answer: str
    evidence_status: EvidenceStatus
    citation_chunk_ids: list[str]


class LLMProvider(Protocol):
    def generate_structured(self, prompt: str, response_model: type[T]) -> T: ...


class GeminiLLMProvider:
    def __init__(self, api_key: str | None, model: str) -> None:
        if not api_key:
            raise RuntimeError("LLM_API_KEY is required for agent generation.")
        self.client = genai.Client(api_key=api_key)
        self.model = model

    def generate_structured(self, prompt: str, response_model: type[T]) -> T:
        response = self.client.models.generate_content(model=self.model, contents=prompt, config=types.GenerateContentConfig(response_mime_type="application/json", response_schema=response_model))
        return response_model.model_validate(json.loads(response.text or "{}"))
