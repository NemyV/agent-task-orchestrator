from sqlalchemy import func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.db import JobRow


class JobRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def get(self, job_id: str) -> JobRow | None:
        return self.session.get(JobRow, job_id)

    def get_by_idempotency_key(self, key: str) -> JobRow | None:
        statement = select(JobRow).where(JobRow.idempotency_key == key)
        return self.session.scalar(statement)

    def add(self, row: JobRow) -> JobRow:
        self.session.add(row)
        try:
            self.session.commit()
        except IntegrityError:
            self.session.rollback()
            existing = self.get_by_idempotency_key(row.idempotency_key)
            if existing is None:
                raise
            return existing
        self.session.refresh(row)
        return row

    def save(self, row: JobRow) -> JobRow:
        self.session.add(row)
        self.session.commit()
        self.session.refresh(row)
        return row

    def claim_for_execution(self, job_id: str, max_attempts: int) -> JobRow | None:
        """Atomically move one runnable job to ``running`` and increment its attempt count.

        The conditional UPDATE is the concurrency boundary: if two API/worker processes race for
        the same job, only one can change an eligible row. PostgreSQL re-checks the predicate after
        waiting on the row lock, so the loser observes zero updated rows instead of double-running.
        """
        statement = (
            update(JobRow)
            .where(
                JobRow.id == job_id,
                JobRow.status.in_(["pending", "failed"]),
                JobRow.attempts < max_attempts,
            )
            .values(
                status="running",
                attempts=JobRow.attempts + 1,
                result=None,
                verification=None,
                error=None,
            )
            .returning(JobRow)
        )
        claimed = self.session.scalars(statement).one_or_none()
        if claimed is None:
            self.session.rollback()
            return None
        self.session.commit()
        return claimed

    def list_runnable_ids(self, max_attempts: int, limit: int = 20) -> list[str]:
        statement = (
            select(JobRow.id)
            .where(
                JobRow.status.in_(["pending", "failed"]),
                JobRow.attempts < max_attempts,
            )
            .order_by(JobRow.updated_at.asc(), JobRow.created_at.asc())
            .limit(limit)
        )
        return list(self.session.scalars(statement))

    def status_counts(self) -> dict[str, int]:
        statement = select(JobRow.status, func.count(JobRow.id)).group_by(JobRow.status)
        return {status: count for status, count in self.session.execute(statement)}
