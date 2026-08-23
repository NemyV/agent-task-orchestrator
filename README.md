# Agent Task Orchestrator

A small production-style Python service built as a portfolio project for backend/AI-agent engineering roles.

The goal is not to build another chat UI. The project demonstrates the engineering around supervised AI work: bounded tasks, explicit state, idempotent requests, verification, API contracts, tests, typing, containerization and CI.

## Current milestone

- FastAPI REST API with automatic OpenAPI documentation
- Pydantic request/response validation
- Explicit job lifecycle: `pending -> running -> completed`
- Idempotency keys to prevent duplicate job creation
- Separate service/domain layer rather than putting logic directly in HTTP handlers
- Verification result recorded separately from execution result
- pytest API tests
- Ruff linting and strict mypy configuration
- Docker image
- Docker Compose stack including PostgreSQL
- GitHub Actions CI

The first milestone intentionally keeps the job store in memory. PostgreSQL is already included in the local stack and persistence is the next milestone. This keeps the business rules easy to test before coupling them to infrastructure.

## Architecture

```text
Client
  |
  v
FastAPI / OpenAPI
  |
  v
Pydantic validation
  |
  v
JobService
  |---- idempotency check
  |---- lifecycle transition
  |---- bounded execution
  `---- verification

Next milestone:
JobService -> repository abstraction -> PostgreSQL
           -> worker queue -> executor -> verifier
```

## Why verification is separate

An AI or automated worker producing output does not mean the task succeeded. The execution result and verification result are modeled separately so the system can later apply deterministic checks, policy checks or a second-model review before a task is accepted.

## Run locally

### Docker

```bash
docker compose up --build
```

Then open:

- API: `http://localhost:8000`
- Swagger/OpenAPI UI: `http://localhost:8000/docs`
- OpenAPI JSON: `http://localhost:8000/openapi.json`

### Python

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e '.[dev]'
uvicorn app.main:app --reload
```

## Example

Create a job:

```bash
curl -X POST http://localhost:8000/jobs \
  -H 'Content-Type: application/json' \
  -d '{
    "goal": "Summarize repository changes and verify the output",
    "requires_confirmation": true,
    "idempotency_key": "portfolio-demo-0001"
  }'
```

Submitting the same idempotency key again returns the original job rather than creating a duplicate.

Run it:

```bash
curl -X POST http://localhost:8000/jobs/<JOB_ID>/run
```

## Quality checks

```bash
ruff check .
mypy app
pytest
```

CI executes all three checks for pushes and pull requests.

## Roadmap

1. PostgreSQL repository implementation and migrations
2. Background worker and retry policy
3. Confirmation endpoint for tasks requiring human approval
4. Structured JSON logging and correlation IDs
5. Executor interface with a safe deterministic demo agent
6. Verification policy and failure states
7. Metrics and health/readiness endpoints
8. Integration tests against PostgreSQL

## Engineering decisions

### Start deterministic
The core executor is deliberately deterministic in milestone one. Agent systems are much easier to reason about when orchestration, state transitions and verification can be tested without an external LLM dependency.

### Idempotency before queues
Retries are normal in distributed systems. Defining duplicate-request behavior before adding a queue avoids a class of double-execution bugs later.

### Keep HTTP thin
FastAPI handlers translate HTTP concerns. Job lifecycle rules stay in the service layer, which makes the domain code independently testable and easier to move behind a worker later.

### Infrastructure is incremental
PostgreSQL is included from the beginning, but the code does not pretend persistence is implemented before it actually is. Each roadmap item should be backed by working code and tests before being claimed as a completed feature.
