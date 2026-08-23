from collections.abc import Generator
from typing import Annotated

from fastapi import Depends, FastAPI, HTTPException, Response, status
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.db import get_session
from app.models import ConfirmationRead, JobCreate, JobRead, JobStatus
from app.repository import JobRepository
from app.service import (
    IdempotencyConflictError,
    InvalidTransitionError,
    JobNotFoundError,
    JobService,
)

app = FastAPI(
    title="Agent Task Orchestrator",
    version="1.1.0",
    description="Supervised, persistent and auditable agent-task orchestration API.",
)


def session_dependency() -> Generator[Session, None, None]:
    yield from get_session()


SessionDep = Annotated[Session, Depends(session_dependency)]


def service_dependency(session: SessionDep) -> JobService:
    return JobService(session)


ServiceDep = Annotated[JobService, Depends(service_dependency)]


@app.get("/", include_in_schema=False)
def root() -> dict[str, str]:
    return {
        "service": "agent-task-orchestrator",
        "version": app.version,
        "docs": "/docs",
        "health": "/health",
    }


@app.get("/health", tags=["system"])
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/ready", tags=["system"])
def ready(session: SessionDep) -> dict[str, str]:
    try:
        session.execute(text("SELECT 1"))
    except SQLAlchemyError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Database is not ready",
        ) from exc
    return {"status": "ready"}


@app.post("/jobs", response_model=JobRead, status_code=status.HTTP_201_CREATED, tags=["jobs"])
def create_job(payload: JobCreate, service: ServiceDep) -> JobRead:
    try:
        return service.create(payload)
    except IdempotencyConflictError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@app.get("/jobs/{job_id}", response_model=JobRead, tags=["jobs"])
def get_job(job_id: str, service: ServiceDep) -> JobRead:
    job = service.get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")
    return job


@app.post("/jobs/{job_id}/confirm", response_model=ConfirmationRead, tags=["jobs"])
def confirm_job(job_id: str, service: ServiceDep) -> ConfirmationRead:
    try:
        return service.confirm(job_id)
    except JobNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Job not found") from exc
    except InvalidTransitionError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@app.post("/jobs/{job_id}/run", response_model=JobRead, tags=["jobs"])
def run_job(job_id: str, service: ServiceDep) -> JobRead:
    try:
        return service.run(job_id)
    except JobNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Job not found") from exc
    except InvalidTransitionError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@app.get("/metrics", tags=["system"], response_class=Response)
def metrics(session: SessionDep) -> Response:
    counts = JobRepository(session).status_counts()
    lines = [
        "# HELP agent_orchestrator_up Process health",
        "# TYPE agent_orchestrator_up gauge",
        "agent_orchestrator_up 1",
        "# HELP agent_orchestrator_jobs Number of persisted jobs by status",
        "# TYPE agent_orchestrator_jobs gauge",
    ]
    for job_status in JobStatus:
        lines.append(
            f'agent_orchestrator_jobs{{status="{job_status.value}"}} '
            f"{counts.get(job_status.value, 0)}"
        )
    return Response(
        content="\n".join(lines) + "\n",
        media_type="text/plain; version=0.0.4",
    )
