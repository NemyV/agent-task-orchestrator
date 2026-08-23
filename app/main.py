from collections.abc import Generator
from typing import Annotated

from fastapi import Depends, FastAPI, HTTPException, Response, status
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.db import Base, engine, get_session
from app.models import ConfirmationRead, JobCreate, JobRead
from app.service import InvalidTransitionError, JobNotFoundError, JobService

Base.metadata.create_all(bind=engine)

app = FastAPI(
    title="Agent Task Orchestrator",
    version="1.0.0",
    description="Supervised, persistent and auditable agent-task orchestration API.",
)


def session_dependency() -> Generator[Session, None, None]:
    yield from get_session()


def service_dependency(session: Annotated[Session, Depends(session_dependency)]) -> JobService:
    return JobService(session)


SessionDep = Annotated[Session, Depends(session_dependency)]
ServiceDep = Annotated[JobService, Depends(service_dependency)]


@app.get("/health", tags=["system"])
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/ready", tags=["system"])
def ready(session: SessionDep) -> dict[str, str]:
    session.execute(text("SELECT 1"))
    return {"status": "ready"}


@app.post("/jobs", response_model=JobRead, status_code=status.HTTP_201_CREATED, tags=["jobs"])
def create_job(payload: JobCreate, service: ServiceDep) -> JobRead:
    return service.create(payload)


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
def metrics() -> Response:
    body = (
        "# HELP agent_orchestrator_up Process health\n"
        "# TYPE agent_orchestrator_up gauge\n"
        "agent_orchestrator_up 1\n"
    )
    return Response(content=body, media_type="text/plain; version=0.0.4")
