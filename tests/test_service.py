from uuid import uuid4

import pytest
from sqlalchemy.orm import Session

from app.db import Base, JobRow, SessionLocal, engine
from app.executor import DeterministicExecutor
from app.models import JobCreate, JobStatus
from app.repository import JobRepository
from app.service import InvalidTransitionError, JobService
from app.verifier import DeterministicVerifier
from app.worker import run_once


class FailingExecutor:
    def execute(self, goal: str) -> object:
        del goal
        raise RuntimeError("simulated executor failure")


@pytest.fixture(autouse=True)
def reset_database() -> None:
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)


def create_runnable_job(session: Session, key: str = "service-key-0001") -> str:
    created = JobService(session).create(
        JobCreate(
            goal="Execute a deterministic retry test",
            requires_confirmation=False,
            idempotency_key=key,
        )
    )
    return created.id


def test_failed_execution_can_retry_and_then_complete() -> None:
    with SessionLocal() as session:
        service = JobService(session, max_attempts=3)
        job_id = create_runnable_job(session)
        service.executor = FailingExecutor()  # type: ignore[assignment]

        failed = service.run(job_id)
        assert failed.status == JobStatus.failed
        assert failed.attempts == 1
        assert failed.error == "RuntimeError: simulated executor failure"

        service.executor = DeterministicExecutor()
        completed = service.run(job_id)
        assert completed.status == JobStatus.completed
        assert completed.attempts == 2
        assert completed.error is None


def test_maximum_attempts_is_enforced() -> None:
    with SessionLocal() as session:
        service = JobService(session, max_attempts=2)
        job_id = create_runnable_job(session, key="service-key-0002")
        service.executor = FailingExecutor()  # type: ignore[assignment]

        assert service.run(job_id).status == JobStatus.failed
        assert service.run(job_id).attempts == 2
        with pytest.raises(InvalidTransitionError, match="maximum execution attempts"):
            service.run(job_id)

        persisted = service.get(job_id)
        assert persisted is not None
        assert persisted.attempts == 2


def test_repository_claim_is_single_winner() -> None:
    with SessionLocal() as session:
        job_id = create_runnable_job(session, key="service-key-0003")
        repo = JobRepository(session)

        first_claim = repo.claim_for_execution(job_id, max_attempts=3)
        second_claim = repo.claim_for_execution(job_id, max_attempts=3)

        assert first_claim is not None
        assert first_claim.status == JobStatus.running.value
        assert first_claim.attempts == 1
        assert second_claim is None


def test_repository_duplicate_insert_returns_existing_row() -> None:
    with SessionLocal() as session:
        repo = JobRepository(session)
        original = JobRow(
            id=str(uuid4()),
            goal="Original request",
            status=JobStatus.pending.value,
            requires_confirmation=False,
            confirmed=True,
            idempotency_key="repository-key-0001",
        )
        saved = repo.add(original)
        duplicate = JobRow(
            id=str(uuid4()),
            goal="Concurrent duplicate request",
            status=JobStatus.pending.value,
            requires_confirmation=False,
            confirmed=True,
            idempotency_key="repository-key-0001",
        )

        winner = repo.add(duplicate)
        assert winner.id == saved.id
        assert winner.goal == "Original request"


def test_verifier_rejects_empty_and_unbounded_output() -> None:
    verifier = DeterministicVerifier()

    empty = verifier.verify("Expected bounded goal", "")
    wrong_goal = verifier.verify("Expected bounded goal", "Executed something else")

    assert empty.passed is False
    assert "no output" in empty.message
    assert wrong_goal.passed is False
    assert "bounded goal" in wrong_goal.message


def test_background_worker_processes_runnable_job() -> None:
    with SessionLocal() as session:
        job_id = create_runnable_job(session, key="service-key-0004")

    assert run_once() == 1

    with SessionLocal() as session:
        row = session.get(JobRow, job_id)
        assert row is not None
        assert row.status == JobStatus.completed.value
        assert row.attempts == 1
