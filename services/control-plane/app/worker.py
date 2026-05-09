"""RQ worker entrypoint.

Run inside the worker container as `python -m app.worker`. Picks jobs
off the agent-runs queue, hands each off to the execution backend, and
keeps going. Crashes/exits in the backend update the run row before
they bubble up to RQ.
"""
from __future__ import annotations

import logging
import uuid

from redis import Redis
from rq import Queue, Worker

from app.core.config import settings
from app.execution.docker_backend import DockerExecutionBackend
from app.execution.job_queue import RqJobQueue

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s | %(message)s")
logger = logging.getLogger(__name__)


def execute_run(run_id_str: str) -> None:
    """Top-level RQ task."""
    run_id = uuid.UUID(run_id_str)
    backend = DockerExecutionBackend()
    try:
        outcome = backend.execute(run_id)
        logger.info(
            "run %s finished status=%s exit_code=%s duration=%.2fs",
            run_id, outcome.status, outcome.exit_code, outcome.duration_seconds,
        )
    except Exception:
        logger.exception("execute_run %s blew up; marking run as failed", run_id)
        from datetime import datetime, timezone
        from app.core.db import SessionLocal
        from app.models import Run, RunStatus

        with SessionLocal() as db:
            run = db.get(Run, run_id)
            if run is not None and run.status not in (RunStatus.succeeded, RunStatus.failed):
                run.status = RunStatus.failed
                run.error = "internal worker error; see logs"
                run.finished_at = datetime.now(timezone.utc)
                db.commit()
        raise


def main() -> None:
    redis = Redis.from_url(settings.redis_url)
    queue = Queue(name=RqJobQueue.QUEUE_NAME, connection=redis)
    logger.info("worker starting; listening on queue=%s", queue.name)
    Worker([queue], connection=redis).work(with_scheduler=False)


if __name__ == "__main__":
    main()
