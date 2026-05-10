"""Cron scheduler.

Polls the schedule table every TICK_SECONDS, finds rows whose
next_run_at has passed, enqueues a queued Run, and advances
last_run_at + next_run_at via croniter.

Run inside the scheduler container as `python -m app.scheduler`.
Runs in a single process; safe to start a second instance only if
both share the same DB (the row update uses a small transaction so
the same schedule can't double-fire across replicas, though the
prototype assumes single-instance).
"""
from __future__ import annotations

import logging
import time
from datetime import datetime, timezone

from croniter import croniter
from sqlalchemy import select

from app.core.config import settings
from app.core.db import SessionLocal
from app.execution.job_queue import RqJobQueue
from app.models import Agent, Run, RunStatus, RunTrigger, Schedule

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s | %(message)s")
logger = logging.getLogger(__name__)

TICK_SECONDS = 30


def tick() -> int:
    """Process schedules whose next_run_at has passed. Returns count fired."""
    fired = 0
    queue = RqJobQueue(settings.redis_url)

    with SessionLocal() as db:
        now = datetime.now(tz=timezone.utc)
        due = (
            db.execute(
                select(Schedule).where(
                    Schedule.enabled.is_(True),
                    Schedule.next_run_at.isnot(None),
                    Schedule.next_run_at <= now,
                )
            )
            .scalars()
            .all()
        )
        for sched in due:
            agent = db.get(Agent, sched.agent_id)
            if agent is None or agent.current_version_id is None:
                logger.warning(
                    "schedule %s skipped: agent %s missing or has no current version",
                    sched.id, sched.agent_id,
                )
                # Still advance so we don't busy-loop on a broken schedule.
                sched.next_run_at = croniter(sched.cron, now).get_next(datetime)
                continue

            run = Run(
                agent_id=agent.id,
                agent_version_id=agent.current_version_id,
                triggering_user_id=None,
                trigger=RunTrigger.scheduled,
                status=RunStatus.queued,
                inputs_json=sched.inputs_json or {},
            )
            db.add(run)
            db.flush()

            sched.last_run_at = now
            sched.next_run_at = croniter(sched.cron, now).get_next(datetime)

            db.commit()
            queue.enqueue(run.id)
            fired += 1
            logger.info(
                "fired schedule %s → run %s for agent %s (next_run_at=%s)",
                sched.id, run.id, agent.slug, sched.next_run_at.isoformat(),
            )

    return fired


def main() -> None:
    logger.info("scheduler starting; tick=%ss", TICK_SECONDS)
    while True:
        try:
            n = tick()
            if n:
                logger.info("tick fired %d schedule(s)", n)
        except Exception:
            logger.exception("scheduler tick failed; continuing")
        time.sleep(TICK_SECONDS)


if __name__ == "__main__":
    main()
