import pytest
from fastapi.testclient import TestClient

from app.db import Base, engine
from app.main import app

client = TestClient(app)


@pytest.fixture(autouse=True)
def reset_database() -> None:
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)


def test_root_health_and_readiness() -> None:
    root = client.get("/")
    health = client.get("/health")
    ready = client.get("/ready")

    assert root.status_code == 200
    assert root.json()["service"] == "agent-task-orchestrator"
    assert root.json()["docs"] == "/docs"
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
    repeated_confirmation = client.post(f"/jobs/{job_id}/confirm")
    assert confirmation.status_code == 200
    assert repeated_confirmation.status_code == 200
    assert confirmation.json()["confirmed"] is True
    assert confirmation.json()["status"] == "pending"

    run = client.post(f"/jobs/{job_id}/run")
    repeated_run = client.post(f"/jobs/{job_id}/run")
    assert run.status_code == 200
    assert repeated_run.status_code == 200
    assert run.json()["status"] == "completed"
    assert run.json()["attempts"] == 1
    assert repeated_run.json()["attempts"] == 1
    assert run.json()["verification"].startswith("verified:")


def test_reusing_idempotency_key_for_different_request_returns_conflict() -> None:
    first = client.post(
        "/jobs",
        json={
            "goal": "Inspect the first bounded task",
            "requires_confirmation": False,
            "idempotency_key": "shared-key-0001",
        },
    )
    conflict = client.post(
        "/jobs",
        json={
            "goal": "A different task must not reuse the key",
            "requires_confirmation": False,
            "idempotency_key": "shared-key-0001",
        },
    )

    assert first.status_code == 201
    assert conflict.status_code == 409
    assert "different request" in conflict.json()["detail"]


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


def test_input_validation_trims_text_and_rejects_invalid_payloads() -> None:
    created = client.post(
        "/jobs",
        json={
            "goal": "   A valid normalized task   ",
            "requires_confirmation": False,
            "idempotency_key": "   normalized-key-0001   ",
        },
    )
    assert created.status_code == 201
    assert created.json()["goal"] == "A valid normalized task"
    assert created.json()["idempotency_key"] == "normalized-key-0001"

    whitespace_only = client.post(
        "/jobs",
        json={
            "goal": "     ",
            "requires_confirmation": False,
            "idempotency_key": "valid-key-0001",
        },
    )
    unknown_field = client.post(
        "/jobs",
        json={
            "goal": "A valid task",
            "requires_confirmation": False,
            "idempotency_key": "valid-key-0002",
            "unexpected": "value",
        },
    )

    assert whitespace_only.status_code == 422
    assert unknown_field.status_code == 422


def test_missing_job_returns_404() -> None:
    response = client.get("/jobs/does-not-exist")
    assert response.status_code == 404


def test_metrics_endpoint_exposes_real_job_counts() -> None:
    client.post(
        "/jobs",
        json={
            "goal": "Remain pending for metrics",
            "requires_confirmation": False,
            "idempotency_key": "metrics-key-0001",
        },
    )

    response = client.get("/metrics")
    assert response.status_code == 200
    assert "agent_orchestrator_up 1" in response.text
    assert 'agent_orchestrator_jobs{status="pending"} 1' in response.text
