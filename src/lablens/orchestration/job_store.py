"""In-memory job store for async analysis tracking.

MVP limitation: single-process, non-durable, lost on restart.
Upgrade path: Redis or SQLite when needed.
"""

import logging
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import Enum

logger = logging.getLogger(__name__)


class JobStatus(str, Enum):
    QUEUED = "queued"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"


@dataclass
class Job:
    id: str
    status: JobStatus
    created_at: datetime
    result: dict | None = None
    error: str | None = None


class JobStore:
    """In-memory job store with TTL cleanup."""

    def __init__(self, ttl_minutes: int = 60):
        self._jobs: dict[str, Job] = {}
        self._ttl = timedelta(minutes=ttl_minutes)

    def create(self) -> str:
        job_id = str(uuid.uuid4())
        self._jobs[job_id] = Job(
            id=job_id, status=JobStatus.QUEUED, created_at=datetime.utcnow()
        )
        self._cleanup()
        return job_id

    def get(self, job_id: str) -> Job | None:
        return self._jobs.get(job_id)

    def update(
        self,
        job_id: str,
        status: JobStatus,
        result: dict | None = None,
        error: str | None = None,
    ):
        job = self._jobs.get(job_id)
        if job:
            job.status = status
            job.result = result
            job.error = error

    def _cleanup(self):
        cutoff = datetime.utcnow() - self._ttl
        expired = [k for k, v in self._jobs.items() if v.created_at < cutoff]
        for k in expired:
            del self._jobs[k]
        if expired:
            logger.info("Cleaned up %d expired jobs", len(expired))
