import uuid

from redis import Redis
from rq import Queue, Retry
from rq.job import Job
from rq.registry import ScheduledJobRegistry

from app.config import Settings
from app.telemetry import inject_trace_context


class AgentQueue:
    def __init__(self, settings: Settings) -> None:
        self.queue = Queue("answerforge-agent", connection=Redis.from_url(settings.redis_url))

    def enqueue(self, run_id: uuid.UUID) -> str:
        job = self.queue.enqueue(
            "app.worker.process_agent_run",
            str(run_id),
            trace_context=inject_trace_context(),
            job_timeout="10m",
            retry=Retry(max=3, interval=[10, 30, 60]),
        )
        return job.id

    def remove_runs(self, run_ids: set[uuid.UUID]) -> None:
        run_ids_as_strings = {str(run_id) for run_id in run_ids}
        queued_job_ids = {job.id for job in self.queue.jobs}
        jobs: dict[str, Job] = {job.id: job for job in self.queue.jobs}
        scheduled = ScheduledJobRegistry(self.queue.name, connection=self.queue.connection)
        for job_id in scheduled.get_job_ids():
            try:
                jobs[job_id] = Job.fetch(job_id, connection=self.queue.connection)
            except Exception:
                continue
        for job in jobs.values():
            if job.args and job.args[0] in run_ids_as_strings:
                if job.id in queued_job_ids:
                    job.cancel()
                    job.delete()
                else:
                    scheduled.remove(job, delete_job=True)


class IngestionQueue:
    def __init__(self, settings: Settings) -> None:
        self.queue = Queue("answerforge-ingestion", connection=Redis.from_url(settings.redis_url))
        self.job_timeout = settings.ingestion_job_timeout_seconds

    def enqueue(self, run_id: uuid.UUID) -> str:
        job = self.queue.enqueue(
            "app.worker.process_ingestion_run",
            str(run_id),
            trace_context=inject_trace_context(),
            job_timeout=self.job_timeout,
            retry=Retry(max=3, interval=[30, 120, 300]),
        )
        return job.id
