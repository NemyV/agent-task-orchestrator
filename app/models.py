from enum import StrEnum

from pydantic import BaseModel, Field


class JobStatus(StrEnum):
    pending = "pending"
    running = "running"
    completed = "completed"
    failed = "failed"


class JobCreate(BaseModel):
    goal: str = Field(min_length=5, max_length=500)
    requires_confirmation: bool = True
    idempotency_key: str = Field(min_length=8, max_length=100)


class JobRead(BaseModel):
    id: str
    goal: str
    status: JobStatus
    requires_confirmation: bool
    idempotency_key: str
    result: str | None = None
    verification: str | None = None
