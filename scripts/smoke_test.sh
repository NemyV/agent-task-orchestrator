#!/usr/bin/env bash
set -euo pipefail

base_url="${BASE_URL:-http://localhost:8000}"

for _ in $(seq 1 60); do
  if curl -fsS "${base_url}/ready" >/dev/null; then
    break
  fi
  sleep 1
done
curl -fsS "${base_url}/ready" >/dev/null

created="$(curl -fsS -X POST "${base_url}/jobs" \
  -H 'Content-Type: application/json' \
  -d '{
    "goal": "Run the end-to-end container smoke test",
    "requires_confirmation": false,
    "idempotency_key": "docker-smoke-0001"
  }')"
job_id="$(printf '%s' "${created}" | python -c 'import json,sys; print(json.load(sys.stdin)["id"])')"

final_status=""
for _ in $(seq 1 60); do
  job="$(curl -fsS "${base_url}/jobs/${job_id}")"
  final_status="$(printf '%s' "${job}" | python -c 'import json,sys; print(json.load(sys.stdin)["status"])')"
  if [[ "${final_status}" == "completed" ]]; then
    break
  fi
  if [[ "${final_status}" == "failed" ]]; then
    printf 'Smoke-test job failed: %s\n' "${job}" >&2
    exit 1
  fi
  sleep 1
done

if [[ "${final_status}" != "completed" ]]; then
  printf 'Smoke-test job did not complete; last status=%s\n' "${final_status}" >&2
  exit 1
fi

curl -fsS "${base_url}/metrics" | grep -q 'agent_orchestrator_jobs{status="completed"} 1'
printf 'End-to-end smoke test passed for job %s\n' "${job_id}"
