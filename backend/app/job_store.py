from __future__ import annotations

from datetime import datetime, timezone
from threading import Lock
from uuid import uuid4

from .models import MigrationJob, MigrationStage


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


class JobStore:
    def __init__(self) -> None:
        self._jobs: dict[str, MigrationJob] = {}
        self._lock = Lock()

    def create(self, requested_dashboards: int) -> MigrationJob:
        now = utc_now()
        job = MigrationJob(
            id=str(uuid4()),
            status="queued",
            requested_dashboards=requested_dashboards,
            progress=MigrationStage(percent=0, stage="queued", detail="Migration job accepted"),
            created_at=now,
            updated_at=now,
        )
        with self._lock:
            self._jobs[job.id] = job
        return job

    def get(self, job_id: str) -> MigrationJob | None:
        with self._lock:
            return self._jobs.get(job_id)

    def update(self, job_id: str, **changes) -> MigrationJob:
        with self._lock:
            job = self._jobs[job_id]
            data = job.model_dump()
            data.update(changes)
            data["updated_at"] = utc_now()
            updated = MigrationJob(**data)
            self._jobs[job_id] = updated
            return updated


jobs = JobStore()
