from __future__ import annotations

from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, Field


class SiiCredentials(BaseModel):
    login_url: str
    target_menu_url: str
    username_rut: str
    password: str
    certificate_password: str


class GuideDefaults(BaseModel):
    seller_name: str
    recipient_name: str
    recipient_rut: str
    recipient_business: str
    recipient_address: str
    recipient_city: str
    recipient_commune: str
    transfer_type: str
    transporter_rut: str
    vehicle_patent: str
    driver_rut: str
    driver_name: str
    auto_description: str
    bus_description: str
    unit_price: int = 1
    reference_prefix: str


class RuntimeOptions(BaseModel):
    headless: bool = True
    slow_mo_ms: int = 0
    timeout_ms: int = 30000


class DispatchGuideRequest(BaseModel):
    issue_date: date
    note_label: str
    auto_units: int = 0
    bus_units: int = 0


class DispatchGuideBatchRequest(BaseModel):
    tenant_id: str
    instance_id: str | None = None
    job_name: str | None = None
    credentials: SiiCredentials | None = None
    defaults: GuideDefaults | None = None
    runtime: RuntimeOptions | None = None
    guides: list[DispatchGuideRequest] = Field(default_factory=list)


class PdfArtifact(BaseModel):
    guide: str
    issue_date: str
    folio: str
    file_name: str
    file_path: str


class JobResult(BaseModel):
    artifacts_dir: str
    downloads_dir: str
    pdfs: list[PdfArtifact] = Field(default_factory=list)


class JobRecord(BaseModel):
    id: str
    job_type: Literal["dispatch_guides"]
    tenant_id: str
    instance_id: str | None = None
    job_name: str | None = None
    status: Literal["queued", "running", "succeeded", "failed"]
    created_at: datetime
    updated_at: datetime
    error: str | None = None
    result: JobResult | None = None
