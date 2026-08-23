from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field


class JobStatus(StrEnum):
    pending = "pending"
    running = "running"
    waiting_confirmation = "waiting_confirmation"
    completed = "completed"
    failed = "failed"


class JobCreate(BaseModel):
    goal: str = Field(min_length=5, max_length=500)
    requires_confirmation: bool = True
    idempotency_key: str = Field(min_length=8, max_length=100)


class JobRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    goal: str
    status: JobStatus
    requires_confirmation: bool
    confirmed: bool
    idempotency_key: str
    result: str | None = None
    verification: str | None = None
    attempts: int
    error: str | None = None
    created_at: datetime
    updated_at: datetime


class ConfirmationRead(BaseModel):
    id: str
    confirmed: bool
    status: JobStatus
