# Agent Task Orchestrator

A production-style Python backend that demonstrates how AI/automation tasks can be submitted, approved, executed, verified and persisted safely instead of treating generated output as automatically successful.

The service is intentionally deterministic by default: no external LLM key is required to run the project. This keeps the orchestration, persistence, state transitions and verification behavior reproducible and testable.

## What this project demonstrates

- FastAPI REST API and generated OpenAPI documentation
- Pydantic request/response validation
- PostgreSQL persistence through SQLAlchemy 2
- Alembic database migrations
- Idempotent job creation backed by a database uniqueness constraint
- Explicit lifecycle states: `waiting_confirmation -> pending -> running -> completed/failed`
- Human confirmation before execution for sensitive tasks
- Separate executor and verifier abstractions
- Background worker with bounded retry attempts
- Health, readiness and Prometheus-compatible metrics endpoints
- Docker image and Docker Compose stack
- pytest API coverage
- Ruff linting and strict mypy type checking
- GitHub Actions CI

## Architecture

```text
                         +------------------+
Client ---------------->| FastAPI / OpenAPI|
                         +--------+---------+
                                  |
                                  v
                         +------------------+
                         |    JobService    |
                         +---+----------+---+
                             |          |
                    persist  |          | execute
                             v          v
                    +-------------+  +-------------+
                    | Repository  |  |  Executor   |
                    | SQLAlchemy  |  | deterministic|
                    +------+------+  +------+------+ 
                           |                |
                           v                v
                    +-------------+  +-------------+
                    | PostgreSQL  |  |  Verifier   |
                    +-------------+  +-------------+

Background worker polls eligible `pending` jobs and uses the same service layer.
```

## Job lifecycle

```text
requires confirmation                no confirmation required
        |                                      |
        v                                      v
waiting_confirmation ----------------------> pending
        | confirm                              |
        +--------------------------------------+ 
                                               |
                                               v
                                            running
                                            /     \
                                           v       v
                                     completed   failed
```

The execution result and verification result are stored separately. A worker producing output is not treated as proof that the task succeeded.

## Run with Docker

```bash
docker compose up --build
```

The stack starts:

- `api` — FastAPI service on port `8000`
- `worker` — background task worker
- `db` — PostgreSQL 16

Database migrations run automatically when the API and worker containers start.

Useful endpoints:

- API root/docs: `http://localhost:8000/docs`
- OpenAPI schema: `http://localhost:8000/openapi.json`
- Health: `http://localhost:8000/health`
- Readiness/database check: `http://localhost:8000/ready`
- Metrics: `http://localhost:8000/metrics`

## Demo

Create a job that requires human approval:

```bash
curl -s -X POST http://localhost:8000/jobs \
  -H 'Content-Type: application/json' \
  -d '{
    "goal": "Summarize repository changes and verify the output",
    "requires_confirmation": true,
    "idempotency_key": "portfolio-demo-0001"
  }'
```

The job is stored as `waiting_confirmation`. Repeating the same request with the same idempotency key returns the existing job instead of inserting a duplicate.

Confirm it:

```bash
curl -s -X POST http://localhost:8000/jobs/<JOB_ID>/confirm
```

The job becomes `pending`. The worker can then execute it automatically, or it can be run directly for demonstration:

```bash
curl -s -X POST http://localhost:8000/jobs/<JOB_ID>/run
```

Fetch the persisted result:

```bash
curl -s http://localhost:8000/jobs/<JOB_ID>
```

## Local development

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e '.[dev]'
alembic upgrade head
uvicorn app.main:app --reload
```

In another terminal:

```bash
python -m app.worker
```

Without `DATABASE_URL`, local development defaults to SQLite. Docker Compose configures PostgreSQL automatically.

## Quality checks

```bash
ruff check .
mypy app
pytest
```

The same checks run in GitHub Actions on pushes and pull requests.

## Why these design choices?

### Deterministic executor first
Agent infrastructure is easier to test when orchestration does not depend on a nondeterministic external model. The executor interface is intentionally replaceable, so an LLM/tool-calling implementation can be added without rewriting job lifecycle logic.

### Verification is independent
Execution and acceptance are different concerns. Keeping a verifier separate allows deterministic policy checks, schema validation, test execution, a second-model review or other acceptance strategies later.

### Database-backed idempotency
Duplicate HTTP requests and retries are normal. The service checks the idempotency key and PostgreSQL enforces uniqueness as a final consistency boundary.

### Human approval is a state transition
Confirmation is represented explicitly rather than as a UI-only concept. A sensitive job cannot execute until the persisted state records approval.

### Thin HTTP layer
FastAPI handlers translate HTTP concerns. Lifecycle and orchestration rules remain in `JobService`, which is shared by the API and background worker.

## Main technologies

Python 3.12 · FastAPI · Pydantic · SQLAlchemy · PostgreSQL · Alembic · Docker Compose · pytest · mypy · Ruff · GitHub Actions

## Possible extensions

The project is intentionally small enough to review quickly. Natural production extensions would include row-level worker leasing for multi-worker concurrency, Redis/RabbitMQ for queue transport, OpenTelemetry traces, authentication/authorization and a real tool-calling LLM executor.
