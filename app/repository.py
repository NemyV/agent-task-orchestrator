from sqlalchemy import select
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

    def list_pending(self, limit: int = 20) -> list[JobRow]:
        statement = (
            select(JobRow)
            .where(JobRow.status == "pending")
            .order_by(JobRow.created_at.asc())
            .limit(limit)
        )
        return list(self.session.scalars(statement))
