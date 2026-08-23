from fastapi import FastAPI, HTTPException, status

from app.models import JobCreate, JobRead
from app.service import JobService

app = FastAPI(
    title="Agent Task Orchestrator",
    version="0.1.0",
    description="A small API demonstrating supervised, auditable task execution.",
)
service = JobService()


@app.get("/health", tags=["system"])
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/jobs", response_model=JobRead, status_code=status.HTTP_201_CREATED, tags=["jobs"])
def create_job(payload: JobCreate) -> JobRead:
    return service.create(payload)


@app.get("/jobs/{job_id}", response_model=JobRead, tags=["jobs"])
def get_job(job_id: str) -> JobRead:
    job = service.get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")
    return job


@app.post("/jobs/{job_id}/run", response_model=JobRead, tags=["jobs"])
def run_job(job_id: str) -> JobRead:
    try:
        return service.run(job_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Job not found") from exc
