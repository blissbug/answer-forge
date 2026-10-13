from datetime import datetime
from types import SimpleNamespace

from app.services.ingestion import remove_from_knowledge
from app.models import AgentRunStatus
from app.services.queue import AgentQueue
from app.services.review import cancel_queued_agent_runs
from app.services.storage import LocalFileStorage


class FakeDatabase:
    def __init__(self) -> None:
        self.executed = []
        self.committed = False

    def execute(self, statement):  # type: ignore[no-untyped-def]
        self.executed.append(statement)

    def commit(self) -> None:
        self.committed = True

    def refresh(self, document) -> None:  # type: ignore[no-untyped-def]
        pass


def test_remove_preserves_document_and_original_file(tmp_path) -> None:  # type: ignore[no-untyped-def]
    storage = LocalFileStorage(tmp_path / "storage")
    source = tmp_path / "source.txt"
    source.write_text("source", encoding="utf-8")
    import uuid
    workspace_id = uuid.uuid4()
    stored = storage.save(workspace_id, "source.txt", source)
    document = SimpleNamespace(id=uuid.uuid4(), is_deleted=False, deleted_at=None, storage_path=stored)
    database = FakeDatabase()
    result = remove_from_knowledge(database, document)
    assert result is document  # Document identity survives.
    assert document.is_deleted is True
    assert isinstance(document.deleted_at, datetime)
    assert len(database.executed) == 1  # Chunk rows are deleted.
    assert storage.exists(stored)  # The original source stays available.


def test_repeated_removal_is_idempotent() -> None:
    document = SimpleNamespace(id=__import__("uuid").uuid4(), is_deleted=True, deleted_at=datetime.now())
    database = FakeDatabase()
    assert remove_from_knowledge(database, document) is document
    assert database.executed == []


def test_retry_cancels_only_unstarted_agent_runs() -> None:
    queued = SimpleNamespace(id=__import__("uuid").uuid4(), status=AgentRunStatus.QUEUED, completed_at=None, progress_message=None, error_message=None)
    running = SimpleNamespace(id=__import__("uuid").uuid4(), status=AgentRunStatus.RUNNING, completed_at=None, progress_message=None, error_message=None)
    question = SimpleNamespace(agent_runs=[queued, running])

    assert cancel_queued_agent_runs(question) == {queued.id}
    assert queued.status == AgentRunStatus.CANCELLED
    assert queued.completed_at is not None
    assert running.status == AgentRunStatus.RUNNING


def test_retry_removes_a_scheduled_job(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    run_id = __import__("uuid").uuid4()
    job = SimpleNamespace(id="scheduled-job", args=(str(run_id),))
    registry = SimpleNamespace(get_job_ids=lambda: [job.id], remove=lambda removed, delete_job: setattr(registry, "removed", (removed, delete_job)))
    queue = AgentQueue.__new__(AgentQueue)
    queue.queue = SimpleNamespace(jobs=[], name="answerforge-agent", connection=object())

    monkeypatch.setattr("app.services.queue.ScheduledJobRegistry", lambda *_args, **_kwargs: registry)
    monkeypatch.setattr("app.services.queue.Job.fetch", lambda *_args, **_kwargs: job)

    queue.remove_runs({run_id})

    assert registry.removed == (job, True)
