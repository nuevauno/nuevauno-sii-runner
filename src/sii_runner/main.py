from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, Header, HTTPException

from .automation import run_dispatch_guides_job
from .config import RunnerSettings, load_settings
from .jobs import JobStore
from .models import DispatchGuideBatchRequest, JobRecord


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = load_settings()
    app.state.settings = settings
    app.state.jobs = JobStore(settings)
    yield


app = FastAPI(title="NUEVAUNO SII Runner", version="0.1.0", lifespan=lifespan)


def get_settings() -> RunnerSettings:
    return app.state.settings


def get_jobs() -> JobStore:
    return app.state.jobs


def require_api_key(x_runner_key: str | None = Header(default=None)) -> None:
    expected = get_settings().api_key
    if x_runner_key != expected:
        raise HTTPException(status_code=401, detail="Invalid runner API key")


@app.get("/health")
def health() -> dict[str, object]:
    settings = get_settings()
    jobs = get_jobs()
    return {
        "status": "ok",
        "service": "nuevauno-sii-runner",
        "data_root": str(settings.data_root),
        "queued_jobs": len([job for job in jobs.list_jobs() if job.status in {"queued", "running"}]),
    }


@app.get("/v1/jobs")
def list_jobs(_: None = Depends(require_api_key)) -> list[JobRecord]:
    return get_jobs().list_jobs()


@app.get("/v1/jobs/{job_id}")
def get_job(job_id: str, _: None = Depends(require_api_key)) -> JobRecord:
    record = get_jobs().get_job(job_id)
    if not record:
        raise HTTPException(status_code=404, detail="Job not found")
    return record


@app.post("/v1/dispatch-guides/jobs", status_code=202)
def create_dispatch_guides_job(
    request: DispatchGuideBatchRequest,
    _: None = Depends(require_api_key),
) -> JobRecord:
    if not request.guides:
        raise HTTPException(status_code=400, detail="At least one guide is required")
    jobs = get_jobs()
    settings = get_settings()
    return jobs.create_dispatch_job(
        request,
        lambda job_id, payload: run_dispatch_guides_job(settings, job_id, payload),
    )
