import logging
import time

from app.db import SessionLocal
from app.models import JobStatus
from app.repository import JobRepository
from app.service import JobService
from app.settings import get_settings

logging.basicConfig(
    level=logging.INFO,
    format='{"level":"%(levelname)s","logger":"%(name)s","message":"%(message)s"}',
)
logger = logging.getLogger("agent-worker")


def run_once() -> int:
    settings = get_settings()
    processed = 0
    with SessionLocal() as session:
        repo = JobRepository(session)
        jobs = repo.list_pending(limit=20)
        for row in jobs:
            if row.attempts >= settings.max_attempts:
                row.status = JobStatus.failed.value
                row.error = "maximum attempts exceeded"
                repo.save(row)
                continue
            logger.info("processing job=%s attempt=%s", row.id, row.attempts + 1)
            JobService(session).run(row.id)
            processed += 1
    return processed


def main() -> None:
    settings = get_settings()
    logger.info("worker started id=%s", settings.worker_id)
    while True:
        processed = run_once()
        if processed == 0:
            time.sleep(settings.worker_poll_seconds)


if __name__ == "__main__":
    main()
