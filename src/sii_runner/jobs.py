from __future__ import annotations

import json
import threading
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

from .config import RunnerSettings
from .models import DispatchGuideBatchRequest, JobRecord, JobResult


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class JobStore:
    def __init__(self, settings: RunnerSettings):
        self.settings = settings
        self.lock = threading.Lock()
        self.executor = ThreadPoolExecutor(max_workers=settings.max_workers)
        self.jobs: dict[str, JobRecord] = {}
        self._load_existing()

    def _job_path(self, job_id: str) -> Path:
        return self.settings.jobs_dir / f"{job_id}.json"

    def _persist(self, record: JobRecord) -> None:
        self._job_path(record.id).write_text(
            json.dumps(record.model_dump(mode="json"), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def _load_existing(self) -> None:
        for path in sorted(self.settings.jobs_dir.glob("*.json")):
            try:
                record = JobRecord.model_validate_json(path.read_text(encoding="utf-8"))
            except Exception:
                continue
            self.jobs[record.id] = record

    def create_dispatch_job(
        self,
        request: DispatchGuideBatchRequest,
        runner: Callable[[str, DispatchGuideBatchRequest], JobResult],
    ) -> JobRecord:
        job_id = f"job_{uuid.uuid4().hex[:16]}"
        record = JobRecord(
            id=job_id,
            job_type="dispatch_guides",
            tenant_id=request.tenant_id,
            instance_id=request.instance_id,
            job_name=request.job_name,
            status="queued",
            created_at=utcnow(),
            updated_at=utcnow(),
        )
        with self.lock:
            self.jobs[job_id] = record
            self._persist(record)
        self.executor.submit(self._run_dispatch_job, job_id, request, runner)
        return record

    def _update(self, record: JobRecord) -> None:
        record.updated_at = utcnow()
        with self.lock:
            self.jobs[record.id] = record
            self._persist(record)

    def _run_dispatch_job(
        self,
        job_id: str,
        request: DispatchGuideBatchRequest,
        runner: Callable[[str, DispatchGuideBatchRequest], JobResult],
    ) -> None:
        record = self.jobs[job_id]
        record.status = "running"
        self._update(record)
        try:
            result = runner(job_id, request)
            record.status = "succeeded"
            record.result = result
            record.error = None
        except Exception as exc:
            record.status = "failed"
            record.error = str(exc)
        self._update(record)

    def list_jobs(self) -> list[JobRecord]:
        with self.lock:
            return sorted(self.jobs.values(), key=lambda item: item.created_at, reverse=True)

    def get_job(self, job_id: str) -> JobRecord | None:
        with self.lock:
            return self.jobs.get(job_id)
