from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    database_url: str = "postgresql+psycopg://answerforge:answerforge@localhost:5432/answerforge"
    storage_path: Path = Path("./storage")
    max_upload_size_mb: int = 20
    embedding_api_key: str | None = None
    gemini_api_key: str | None = None
    embedding_model: str = "gemini-embedding-2"
    embedding_dimensions: int = 1536
    chunk_size: int = 1200
    chunk_overlap: int = 180
    cors_origins: str = "http://localhost:3000,http://127.0.0.1:3000"
    redis_url: str = "redis://localhost:6379/0"
    llm_api_key: str | None = None
    llm_model: str = "gemini-3.6-flash"
    max_retrieval_rounds: int = 3
    agent_retrieval_top_k: int = 5
    agent_worker_concurrency: int = 2
    hybrid_retrieval_enabled: bool = True
    retrieval_candidate_multiplier: int = 5
    retrieval_candidate_minimum: int = 50
    ingestion_job_timeout_seconds: int = 1200
    otel_enabled: bool = False
    otel_service_name: str = "answerforge-api"
    otel_exporter_otlp_endpoint: str | None = None

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    @property
    def generation_api_key(self) -> str | None:
        """Prefer a dedicated generation key, then retain Stage 1 Gemini compatibility."""
        return self.llm_api_key or self.gemini_api_key or self.embedding_api_key


@lru_cache
def get_settings() -> Settings:
    return Settings()
