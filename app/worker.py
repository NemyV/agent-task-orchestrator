import logging
import time

from app.db import SessionLocal
from app.repository import JobRepository
from app.service import InvalidTransitionError, JobNotFoundError, JobService
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
        job_ids = repo.list_runnable_ids(settings.max_attempts, limit=20)

        for job_id in job_ids:
            try:
                result = JobService(session, max_attempts=settings.max_attempts).run(job_id)
            except (InvalidTransitionError, JobNotFoundError):
                # Another worker/API process may have claimed the same candidate after our list
                # query. The service's atomic claim is authoritative, so this is a normal race.
                logger.info("skipped job=%s because it is no longer runnable", job_id)
                continue

            processed += 1
            logger.info(
                "processed job=%s status=%s attempt=%s",
                result.id,
                result.status,
                result.attempts,
            )
    return processed


def main() -> None:
    settings = get_settings()
    logger.info("worker started id=%s", settings.worker_id)
    while True:
        run_once()
        time.sleep(settings.worker_poll_seconds)


if __name__ == "__main__":
    main()
