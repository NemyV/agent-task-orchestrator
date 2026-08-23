from uuid import uuid4

from sqlalchemy.orm import Session

from app.db import JobRow
from app.executor import DeterministicExecutor
from app.models import ConfirmationRead, JobCreate, JobRead, JobStatus
from app.repository import JobRepository
from app.settings import get_settings
from app.verifier import DeterministicVerifier


class JobNotFoundError(KeyError):
    pass


class InvalidTransitionError(RuntimeError):
    pass


class IdempotencyConflictError(RuntimeError):
    pass


class JobService:
    def __init__(self, session: Session, max_attempts: int | None = None) -> None:
        self.repo = JobRepository(session)
        self.executor = DeterministicExecutor()
        self.verifier = DeterministicVerifier()
        self.max_attempts = max_attempts or get_settings().max_attempts

    @staticmethod
    def _read(row: JobRow) -> JobRead:
        return JobRead.model_validate(row)

    @staticmethod
    def _matches_request(row: JobRow, payload: JobCreate) -> bool:
        return (
            row.goal == payload.goal
            and row.requires_confirmation == payload.requires_confirmation
        )

    def create(self, payload: JobCreate) -> JobRead:
        existing = self.repo.get_by_idempotency_key(payload.idempotency_key)
        if existing is not None:
            if not self._matches_request(existing, payload):
                raise IdempotencyConflictError(
                    "Idempotency key was already used for a different request"
                )
            return self._read(existing)

        initial_status = (
            JobStatus.waiting_confirmation
            if payload.requires_confirmation
            else JobStatus.pending
        )
        row = JobRow(
            id=str(uuid4()),
            goal=payload.goal,
            status=initial_status.value,
            requires_confirmation=payload.requires_confirmation,
            confirmed=not payload.requires_confirmation,
            idempotency_key=payload.idempotency_key,
        )
        saved = self.repo.add(row)

        # A concurrent request can win the database uniqueness race after our first lookup.
        if not self._matches_request(saved, payload):
            raise IdempotencyConflictError(
                "Idempotency key was already used for a different request"
            )
        return self._read(saved)

    def get(self, job_id: str) -> JobRead | None:
        row = self.repo.get(job_id)
        return self._read(row) if row is not None else None

    def confirm(self, job_id: str) -> ConfirmationRead:
        row = self.repo.get(job_id)
        if row is None:
            raise JobNotFoundError(job_id)
        if not row.requires_confirmation:
            raise InvalidTransitionError("Job does not require confirmation")

        # Confirmation is intentionally idempotent. Network retries must not turn a successful
        # approval into a conflict just because the original response was lost.
        if row.confirmed:
            return ConfirmationRead(
                id=row.id,
                confirmed=True,
                status=JobStatus(row.status),
            )
        if row.status != JobStatus.waiting_confirmation.value:
            raise InvalidTransitionError(f"Cannot confirm job in status {row.status}")

        row.confirmed = True
        row.status = JobStatus.pending.value
        saved = self.repo.save(row)
        return ConfirmationRead(
            id=saved.id,
            confirmed=saved.confirmed,
            status=JobStatus(saved.status),
        )

    def run(self, job_id: str) -> JobRead:
        row = self.repo.get(job_id)
        if row is None:
            raise JobNotFoundError(job_id)
        if row.requires_confirmation and not row.confirmed:
            raise InvalidTransitionError("Job requires confirmation before execution")
        if row.status == JobStatus.completed.value:
            return self._read(row)
        if row.status == JobStatus.running.value:
            raise InvalidTransitionError("Job is already running")
        if row.status == JobStatus.failed.value and row.attempts >= self.max_attempts:
            raise InvalidTransitionError("Job exhausted its maximum execution attempts")

        claimed = self.repo.claim_for_execution(job_id, self.max_attempts)
        if claimed is None:
            latest = self.repo.get(job_id)
            if latest is None:
                raise JobNotFoundError(job_id)
            if latest.status == JobStatus.completed.value:
                return self._read(latest)
            raise InvalidTransitionError(f"Cannot run job in status {latest.status}")

        try:
            execution = self.executor.execute(claimed.goal)
            verification = self.verifier.verify(claimed.goal, execution.output)
            claimed.result = execution.output
            claimed.verification = verification.message
            claimed.status = (
                JobStatus.completed.value if verification.passed else JobStatus.failed.value
            )
            if not verification.passed:
                claimed.error = verification.message
        except Exception as exc:
            claimed.status = JobStatus.failed.value
            claimed.error = f"{type(exc).__name__}: {exc}"
        return self._read(self.repo.save(claimed))
