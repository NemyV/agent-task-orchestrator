from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_health() -> None:
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_create_is_idempotent_and_job_can_run() -> None:
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

    job_id = first.json()["id"]
    run = client.post(f"/jobs/{job_id}/run")

    assert run.status_code == 200
    assert run.json()["status"] == "completed"
    assert run.json()["verification"].startswith("verified:")


def test_missing_job_returns_404() -> None:
    response = client.get("/jobs/does-not-exist")
    assert response.status_code == 404
