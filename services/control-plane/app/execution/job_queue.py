"""Job queue interface.

Wraps RQ today; designed so a Temporal-backed implementation could
slot in without touching callers.
"""
from __future__ import annotations

import uuid
from abc import ABC, abstractmethod

from redis import Redis
from rq import Queue


class JobQueue(ABC):
    @abstractmethod
    def enqueue(self, run_id: uuid.UUID) -> str:
        """Enqueue a job to execute `run_id`. Returns the queue's job id."""


class RqJobQueue(JobQueue):
    QUEUE_NAME = "agent-runs"

    def __init__(self, redis_url: str) -> None:
        self._connection = Redis.from_url(redis_url)
        self._queue = Queue(name=self.QUEUE_NAME, connection=self._connection)

    def enqueue(self, run_id: uuid.UUID) -> str:
        # Late import — avoids circular imports between worker.py and the API.
        from app.worker import execute_run

        job = self._queue.enqueue(
            execute_run, str(run_id),
            job_timeout=3600,
            result_ttl=86400,
            failure_ttl=86400,
        )
        return job.id
