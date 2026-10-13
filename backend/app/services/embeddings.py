import logging
from typing import Protocol

from google import genai
from google.genai import types

logger = logging.getLogger("uvicorn.error")
GEMINI_MAX_EMBEDDING_BATCH_SIZE = 100


class EmbeddingError(RuntimeError):
    pass


class EmbeddingService(Protocol):
    def embed_texts(self, texts: list[str]) -> list[list[float]]: ...
    def embed_query(self, query: str) -> list[float]: ...


class GeminiEmbeddingService:
    """Gemini text embeddings for asymmetric knowledge retrieval."""

    def __init__(self, api_key: str | None, model: str, dimensions: int) -> None:
        if not api_key:
            raise EmbeddingError("GEMINI_API_KEY is required to process and search knowledge.")
        self.client = genai.Client(api_key=api_key)
        self.model = model
        self.dimensions = dimensions

    def embed_texts(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        if self.model == "gemini-embedding-001":
            documents = [types.Content(parts=[types.Part(text=text)]) for text in texts]
            return self._embed_in_batches(documents, task_type="RETRIEVAL_DOCUMENT")
        documents = [types.Content(parts=[types.Part(text=f"title: none | text: {text}")]) for text in texts]
        return self._embed_in_batches(documents)

    def embed_query(self, query: str) -> list[float]:
        if self.model == "gemini-embedding-001":
            query_content = types.Content(parts=[types.Part(text=query)])
            return self._embed([query_content], task_type="RETRIEVAL_QUERY")[0]
        query_content = types.Content(parts=[types.Part(text=f"task: search result | query: {query}")])
        return self._embed([query_content])[0]

    def _embed_in_batches(self, contents: list[types.Content], task_type: str | None = None) -> list[list[float]]:
        vectors: list[list[float]] = []
        for start in range(0, len(contents), GEMINI_MAX_EMBEDDING_BATCH_SIZE):
            vectors.extend(self._embed(contents[start:start + GEMINI_MAX_EMBEDDING_BATCH_SIZE], task_type=task_type))
        return vectors

    def _embed(self, contents: list[types.Content], task_type: str | None = None) -> list[list[float]]:
        try:
            logger.info("gemini_embedding_request model=%s dimensions=%s inputs=%s task_type=%s", self.model, self.dimensions, len(contents), task_type or "prompt_prefix")
            config = types.EmbedContentConfig(output_dimensionality=self.dimensions, task_type=task_type)
            response = self.client.models.embed_content(
                model=self.model,
                contents=contents,
                config=config,
            )
            vectors = [list(item.values) for item in response.embeddings or []]
            if len(vectors) != len(contents):
                raise EmbeddingError("Gemini returned an unexpected number of embeddings.")
            logger.info("gemini_embedding_success model=%s dimensions=%s vectors=%s", self.model, self.dimensions, len(vectors))
            return vectors
        except EmbeddingError:
            raise
        except Exception as error:
            message = str(error).lower()
            status_code = getattr(error, "status_code", None) or getattr(error, "code", None) or "unknown"
            logger.warning("gemini_embedding_failure model=%s dimensions=%s inputs=%s task_type=%s error_type=%s status=%s", self.model, self.dimensions, len(contents), task_type or "prompt_prefix", type(error).__name__, status_code)
            if "api key" in message or "permission_denied" in message or "unauthenticated" in message:
                raise EmbeddingError("Gemini rejected the API key. Check GEMINI_API_KEY and its project permissions.") from error
            if "quota" in message or "resource_exhausted" in message:
                raise EmbeddingError("Gemini embedding quota is exhausted or unavailable. Check the Google AI Studio project quota and billing, then retry.") from error
            if "not found" in message or "not supported" in message:
                raise EmbeddingError(f"Gemini model '{self.model}' is unavailable for embeddings. Check EMBEDDING_MODEL.") from error
            raise EmbeddingError("Gemini embedding request failed. Check the model, API key, and provider status.") from error
