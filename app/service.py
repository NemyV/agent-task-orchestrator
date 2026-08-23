from uuid import uuid4

from sqlalchemy.orm import Session

from app.db import JobRow
from app.executor import DeterministicExecutor
from app.models import ConfirmationRead, JobCreate, JobRead, JobStatus
from app.repository import JobRepository
from app.verifier import DeterministicVerifier


class JobNotFoundError(KeyError):
    pass


class InvalidTransitionError(RuntimeError):
    pass


class JobService:
    def __init__(self, session: Session) -> None:
        self.repo = JobRepository(session)
        self.executor = DeterministicExecutor()
        self.verifier = DeterministicVerifier()

    @staticmethod
    def _read(row: JobRow) -> JobRead:
        return JobRead.model_validate(row)

    def create(self, payload: JobCreate) -> JobRead:
        existing = self.repo.get_by_idempotency_key(payload.idempotency_key)
        if existing is not None:
            return self._read(existing)

        status = (
            JobStatus.waiting_confirmation
            if payload.requires_confirmation
            else JobStatus.pending
        )
        row = JobRow(
            id=str(uuid4()),
            goal=payload.goal,
            status=status.value,
            requires_confirmation=payload.requires_confirmation,
            confirmed=not payload.requires_confirmation,
            idempotency_key=payload.idempotency_key,
        )
        return self._read(self.repo.add(row))

    def get(self, job_id: str) -> JobRead | None:
        row = self.repo.get(job_id)
        return self._read(row) if row is not None else None

    def confirm(self, job_id: str) -> ConfirmationRead:
        row = self.repo.get(job_id)
        if row is None:
            raise JobNotFoundError(job_id)
        if not row.requires_confirmation:
            raise InvalidTransitionError("Job does not require confirmation")
        if row.status != JobStatus.waiting_confirmation.value:
            raise InvalidTransitionError(f"Cannot confirm job in status {row.status}")

        row.confirmed = True
        row.status = JobStatus.pending.value
        saved = self.repo.save(row)
        return ConfirmationRead(id=saved.id, confirmed=saved.confirmed, status=JobStatus(saved.status))

    def run(self, job_id: str) -> JobRead:
        row = self.repo.get(job_id)
        if row is None:
            raise JobNotFoundError(job_id)
        if row.requires_confirmation and not row.confirmed:
            raise InvalidTransitionError("Job requires confirmation before execution")
        if row.status not in {JobStatus.pending.value, JobStatus.failed.value}:
            raise InvalidTransitionError(f"Cannot run job in status {row.status}")

        row.status = JobStatus.running.value
        row.attempts += 1
        row.error = None
        self.repo.save(row)

        try:
            execution = self.executor.execute(row.goal)
            verification = self.verifier.verify(row.goal, execution.output)
            row.result = execution.output
            row.verification = verification.message
            row.status = (
                JobStatus.completed.value if verification.passed else JobStatus.failed.value
            )
            if not verification.passed:
                row.error = verification.message
        except Exception as exc:
            row.status = JobStatus.failed.value
            row.error = f"{type(exc).__name__}: {exc}"
        return self._read(self.repo.save(row))
