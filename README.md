# Agent Task Orchestrator

[![CI](https://github.com/NemyV/agent-task-orchestrator/actions/workflows/ci.yml/badge.svg)](https://github.com/NemyV/agent-task-orchestrator/actions/workflows/ci.yml)

A compact Python reference implementation for **supervised and auditable automated task execution**.
It focuses on the backend engineering around agent-style workloads: persistence, idempotency,
human approval, state transitions, bounded retries, concurrent worker safety, independent
verification, migrations, observability endpoints and automated testing.

The default executor is deliberately deterministic and requires **no external AI API key**. That
keeps orchestration behavior reproducible and makes the repository useful for testing the system
around an agent independently from a specific model provider.

## What it demonstrates

- FastAPI REST API with generated OpenAPI documentation
- Pydantic request and response validation
- PostgreSQL persistence through SQLAlchemy 2
- Alembic schema migrations
- database-backed idempotency with conflict detection
- explicit lifecycle states: `waiting_confirmation -> pending -> running -> completed/failed`
- idempotent human confirmation for approval-gated jobs
- atomic execution claims to prevent duplicate execution when workers/API calls race
- bounded retry attempts for failed jobs
- separate executor and verifier components
- background worker using the same domain/service layer as the API
- health, database-readiness and Prometheus-compatible job metrics
- non-root Docker image and Docker Compose stack
- pytest with branch coverage threshold
- Ruff linting and strict mypy type checking
- GitHub Actions CI against both SQLite and PostgreSQL
- full Docker end-to-end smoke test covering API -> PostgreSQL -> worker -> verification

## Architecture

```text
                           +-------------------+
Client ------------------>| FastAPI / OpenAPI |
                           +---------+---------+
                                     |
                                     v
                           +-------------------+
                           |    JobService     |
                           +----+---------+----+
                                |         |
                       persist  |         | execute / verify
                                v         v
                       +-------------+  +-------------+
                       | Repository  |  | Executor    |
                       | SQLAlchemy  |  +------+------+ 
                       +------+------+         |
                              |                v
                              |          +-------------+
                              |          | Verifier    |
                              |          +-------------+
                              v
                       +-------------+
                       | PostgreSQL  |
                       +-------------+
                              ^
                              |
                       +-------------+
                       | Worker      |
                       | polling +   |
                       | atomic claim|
                       +-------------+
```

A one-shot `migrate` container applies Alembic migrations before the API or worker starts. This
avoids having multiple long-running services race to perform schema migrations.

## Job lifecycle

```text
requires confirmation                 no confirmation required
        |                                       |
        v                                       v
waiting_confirmation ---- confirm ----------> pending
                                                |
                                                | atomic claim
                                                v
                                             running
                                             /     \
                                            v       v
                                      completed   failed
                                                    |
                                                    | attempts < MAX_ATTEMPTS
                                                    +---------> retry
```

Execution output and verification output are persisted separately. Producing output is not treated
as proof that a task succeeded.

## Correctness details

### Idempotency

`POST /jobs` accepts an `idempotency_key`. Repeating the **same request** with the same key returns
the existing job. Reusing that key for a different goal or confirmation policy returns HTTP `409`
instead of silently treating two different operations as equivalent.

The application checks the key first, while the database uniqueness constraint remains the final
consistency boundary for concurrent requests.

### Concurrent execution

A candidate job is claimed with a conditional database `UPDATE` that changes an eligible
`pending`/`failed` job to `running` while incrementing its attempt count. If multiple workers, or a
worker and direct API execution, race for the same job, only one claim can succeed.

### Retries

Failed jobs remain eligible while `attempts < MAX_ATTEMPTS`. Every claim increments the persisted
attempt counter before execution, so crashes/failures cannot bypass the retry bound.

### Human approval

Jobs may start in `waiting_confirmation`. Confirmation is persisted and idempotent: retrying a
successful confirmation request is safe. An unconfirmed job cannot be claimed for execution.

## Run the complete stack

```bash
docker compose up --build
```

The stack contains:

- `migrate` — one-shot Alembic migration service
- `api` — FastAPI service on port `8000`
- `worker` — background task worker
- `db` — PostgreSQL 16

Useful endpoints:

- `http://localhost:8000/` — service metadata
- `http://localhost:8000/docs` — Swagger/OpenAPI UI
- `http://localhost:8000/openapi.json` — OpenAPI schema
- `http://localhost:8000/health` — process liveness
- `http://localhost:8000/ready` — database readiness
- `http://localhost:8000/metrics` — Prometheus-compatible status counts

## Demo

Create an approval-gated job:

```bash
curl -s -X POST http://localhost:8000/jobs \
  -H 'Content-Type: application/json' \
  -d '{
    "goal": "Summarize repository changes and verify the output",
    "requires_confirmation": true,
    "idempotency_key": "demo-request-0001"
  }'
```

Confirm it:

```bash
curl -s -X POST http://localhost:8000/jobs/<JOB_ID>/confirm
```

The background worker can now claim and execute it. You can also trigger execution directly:

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
cp .env.example .env
alembic upgrade head
uvicorn app.main:app --reload
```

In another terminal:

```bash
python -m app.worker
```

The sample `.env.example` uses SQLite for a zero-setup development path. Docker Compose uses
PostgreSQL automatically.

## Quality gates

Run locally:

```bash
ruff check .
mypy app
pytest
```

CI performs three independent checks:

1. **Quality / SQLite** — linting, strict type checking and the complete test suite.
2. **PostgreSQL integration** — Alembic upgrade/check/downgrade/upgrade round trip plus tests against PostgreSQL 16.
3. **Docker smoke test** — builds the real images, starts the Compose stack, submits a job through HTTP and waits for the background worker to persist a verified completion.

The test suite enforces branch coverage of at least **85%**.

## Engineering choices

### Deterministic executor first

The orchestration layer can be validated without network access, API keys, model cost or
nondeterministic responses. A real LLM/tool-calling executor can replace the deterministic executor
without changing persistence or lifecycle rules.

### Verification is independent

Execution and acceptance are separate responsibilities. The verifier boundary can later host schema
checks, policy validation, test execution, a second-model review or another acceptance strategy.

### Thin HTTP layer

FastAPI handlers translate HTTP concerns. Lifecycle and orchestration rules live in `JobService`,
which is shared by the API and worker.

### Database as the consistency boundary

Uniqueness and atomic conditional updates provide correctness even when multiple application
processes operate concurrently. Process-local locks would not provide that guarantee.

## Main technologies

Python 3.12 · FastAPI · Pydantic · SQLAlchemy 2 · PostgreSQL · Alembic · Docker Compose · pytest · mypy · Ruff · GitHub Actions

## Deliberate scope

This repository demonstrates orchestration/backend mechanics rather than pretending to be a full
hosted AI platform. It intentionally does **not** include authentication/authorization, a distributed
message broker, a real external LLM integration, OpenTelemetry tracing or multi-tenant isolation.
Those would be natural next steps for a deployed product, but are not required to demonstrate the
core correctness model here.
