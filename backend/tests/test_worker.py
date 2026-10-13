from contextlib import nullcontext
from pathlib import Path
from types import SimpleNamespace
import uuid

from app.services.embeddings import EmbeddingError
import app.worker as worker


def test_ingestion_quota_failure_is_terminal(monkeypatch) -> None:
    run = SimpleNamespace(status=SimpleNamespace(value="QUEUED"), trace_id="trace", document=object())

    class Database:
        def __enter__(self): return self
        def __exit__(self, *_args): return None
        def get(self, *_args): return run
        def rollback(self): return None

    def fail(*_args):
        raise EmbeddingError("quota exhausted")

    outcome = {}
    monkeypatch.setattr(worker, "get_settings", lambda: SimpleNamespace(storage_path=Path("."), gemini_api_key="key", embedding_api_key=None, embedding_model="model", embedding_dimensions=3))
    monkeypatch.setattr(worker, "configure_telemetry", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(worker, "get_current_job", lambda: SimpleNamespace(retries_left=3))
    monkeypatch.setattr(worker, "SessionLocal", Database)
    monkeypatch.setattr(worker, "span", lambda *_args, **_kwargs: nullcontext())
    monkeypatch.setattr(worker, "GeminiEmbeddingService", lambda *_args: object())
    monkeypatch.setattr(worker, "IngestionService", lambda *_args: SimpleNamespace(process=fail))
    monkeypatch.setattr(worker, "mark_ingestion_failed", lambda _db, _run, _message, terminal: outcome.update(terminal=terminal))

    worker.process_ingestion_run(str(uuid.uuid4()))

    assert outcome == {"terminal": True}
