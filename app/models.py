from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field, field_validator


class JobStatus(StrEnum):
    pending = "pending"
    running = "running"
    waiting_confirmation = "waiting_confirmation"
    completed = "completed"
    failed = "failed"


class JobCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    goal: str = Field(min_length=5, max_length=500)
    requires_confirmation: bool = True
    idempotency_key: str = Field(min_length=8, max_length=100)

    @field_validator("goal", "idempotency_key", mode="before")
    @classmethod
    def strip_text_fields(cls, value: object) -> object:
        return value.strip() if isinstance(value, str) else value


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
