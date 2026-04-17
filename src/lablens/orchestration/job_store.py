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
    """In-memory job store with TTL cleanup.

    Phase 3: `touch(job_id)` extends TTL on Q&A interaction (sliding window),
    so chat sessions don't get killed mid-conversation.
    """

    def __init__(
        self, ttl_minutes: int = 60, chat_extend_minutes: int = 240
    ):
        self._jobs: dict[str, Job] = {}
        self._ttl = timedelta(minutes=ttl_minutes)
        self._chat_extend = timedelta(minutes=chat_extend_minutes)

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

    def touch(self, job_id: str) -> bool:
        """Extend TTL on Q&A read.  Sliding window: bumps `created_at`
        forward so the job survives `_chat_extend` minutes from now.

        Returns True if the job exists, False otherwise.
        """
        job = self._jobs.get(job_id)
        if not job:
            return False
        # Move created_at forward so cleanup window restarts.
        job.created_at = datetime.utcnow() - self._ttl + self._chat_extend
        return True

    def _cleanup(self):
        cutoff = datetime.utcnow() - self._ttl
        expired = [k for k, v in self._jobs.items() if v.created_at < cutoff]
        for k in expired:
            del self._jobs[k]
        if expired:
            logger.info("Cleaned up %d expired jobs", len(expired))
