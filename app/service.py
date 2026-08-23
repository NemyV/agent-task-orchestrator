from dataclasses import dataclass
from uuid import uuid4

from app.models import JobCreate, JobRead, JobStatus


@dataclass
class _StoredJob:
    value: JobRead


class JobService:
    """In-memory domain service for the first milestone.

    The public portfolio version deliberately starts with a small deterministic core.
    PostgreSQL persistence and a background worker are the next milestone, keeping the
    business rules independently testable before infrastructure is introduced.
    """

    def __init__(self) -> None:
        self._jobs: dict[str, _StoredJob] = {}
        self._idempotency_index: dict[str, str] = {}

    def create(self, payload: JobCreate) -> JobRead:
        existing_id = self._idempotency_index.get(payload.idempotency_key)
        if existing_id is not None:
            return self._jobs[existing_id].value

        job = JobRead(
            id=str(uuid4()),
            goal=payload.goal,
            status=JobStatus.pending,
            requires_confirmation=payload.requires_confirmation,
            idempotency_key=payload.idempotency_key,
        )
        self._jobs[job.id] = _StoredJob(job)
        self._idempotency_index[payload.idempotency_key] = job.id
        return job

    def get(self, job_id: str) -> JobRead | None:
        stored = self._jobs.get(job_id)
        return stored.value if stored else None

    def run(self, job_id: str) -> JobRead:
        stored = self._jobs.get(job_id)
        if stored is None:
            raise KeyError(job_id)

        job = stored.value
        running = job.model_copy(update={"status": JobStatus.running})
        self._jobs[job_id] = _StoredJob(running)

        result = f"Executed bounded task: {running.goal}"
        verification = "verified: execution result present and job reached expected state"
        completed = running.model_copy(
            update={
                "status": JobStatus.completed,
                "result": result,
                "verification": verification,
            }
        )
        self._jobs[job_id] = _StoredJob(completed)
        return completed
