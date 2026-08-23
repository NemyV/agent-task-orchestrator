import pytest
from fastapi.testclient import TestClient

from app.db import Base, engine
from app.main import app

client = TestClient(app)


@pytest.fixture(autouse=True)
def reset_database() -> None:
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)


def test_health_and_readiness() -> None:
    health = client.get("/health")
    ready = client.get("/ready")
    assert health.status_code == 200
    assert health.json() == {"status": "ok"}
    assert ready.status_code == 200
    assert ready.json() == {"status": "ready"}


def test_create_is_idempotent_confirmation_is_required_and_job_can_run() -> None:
    payload = {
        "goal": "Summarize repository changes and verify the output",
        "requires_confirmation": True,
        "idempotency_key": "demo-key-0001",
    }

    first = client.post("/jobs", json=payload)
    second = client.post("/jobs", json=payload)

    assert first.status_code == 201
    assert second.status_code == 201
    assert first.json()["id"] == second.json()["id"]
    assert first.json()["status"] == "waiting_confirmation"

    job_id = first.json()["id"]
    blocked = client.post(f"/jobs/{job_id}/run")
    assert blocked.status_code == 409

    confirmation = client.post(f"/jobs/{job_id}/confirm")
    assert confirmation.status_code == 200
    assert confirmation.json()["confirmed"] is True
    assert confirmation.json()["status"] == "pending"

    run = client.post(f"/jobs/{job_id}/run")
    assert run.status_code == 200
    assert run.json()["status"] == "completed"
    assert run.json()["attempts"] == 1
    assert run.json()["verification"].startswith("verified:")


def test_job_without_confirmation_can_run_immediately() -> None:
    created = client.post(
        "/jobs",
        json={
            "goal": "Inspect a bounded deterministic task",
            "requires_confirmation": False,
            "idempotency_key": "demo-key-0002",
        },
    )
    assert created.status_code == 201
    assert created.json()["status"] == "pending"

    run = client.post(f"/jobs/{created.json()['id']}/run")
    assert run.status_code == 200
    assert run.json()["status"] == "completed"
    assert run.json()["result"].startswith("Executed bounded task:")


def test_missing_job_returns_404() -> None:
    response = client.get("/jobs/does-not-exist")
    assert response.status_code == 404


def test_metrics_endpoint_is_prometheus_compatible_text() -> None:
    response = client.get("/metrics")
    assert response.status_code == 200
    assert "agent_orchestrator_up 1" in response.text
