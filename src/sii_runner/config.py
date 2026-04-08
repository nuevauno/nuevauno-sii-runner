from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from .models import GuideDefaults, RuntimeOptions, SiiCredentials


def env_bool(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class RunnerSettings:
    data_root: Path
    jobs_dir: Path
    artifacts_dir: Path
    api_key: str
    default_credentials: SiiCredentials
    default_guide_defaults: GuideDefaults
    default_runtime: RuntimeOptions
    max_workers: int


def require_env(name: str) -> str:
    value = os.getenv(name, "").strip()
    if not value:
        raise RuntimeError(f"Missing required environment variable: {name}")
    return value


def load_settings() -> RunnerSettings:
    data_root = Path(os.getenv("RUNNER_DATA_ROOT", "/data/kodo-sii")).resolve()
    jobs_dir = data_root / "jobs"
    artifacts_dir = data_root / "artifacts"
    jobs_dir.mkdir(parents=True, exist_ok=True)
    artifacts_dir.mkdir(parents=True, exist_ok=True)

    credentials = SiiCredentials(
        login_url=require_env("SII_LOGIN_URL"),
        target_menu_url=require_env("SII_TARGET_MENU_URL"),
        username_rut=require_env("SII_USERNAME_RUT"),
        password=require_env("SII_PASSWORD"),
        certificate_password=require_env("SII_CERTIFICATE_PASSWORD"),
    )
    defaults = GuideDefaults(
        seller_name=require_env("SII_SELLER_NAME"),
        recipient_name=require_env("SII_RECIPIENT_NAME"),
        recipient_rut=require_env("SII_RECIPIENT_RUT"),
        recipient_business=require_env("SII_RECIPIENT_BUSINESS"),
        recipient_address=require_env("SII_RECIPIENT_ADDRESS"),
        recipient_city=require_env("SII_RECIPIENT_CITY"),
        recipient_commune=require_env("SII_RECIPIENT_COMMUNE"),
        transfer_type=require_env("SII_TRANSFER_TYPE"),
        transporter_rut=require_env("SII_TRANSPORTER_RUT"),
        vehicle_patent=require_env("SII_VEHICLE_PATENT"),
        driver_rut=require_env("SII_DRIVER_RUT"),
        driver_name=require_env("SII_DRIVER_NAME"),
        auto_description=require_env("SII_AUTO_DESCRIPTION"),
        bus_description=require_env("SII_BUS_DESCRIPTION"),
        unit_price=int(os.getenv("SII_UNIT_PRICE", "1")),
        reference_prefix=require_env("SII_REFERENCE_PREFIX"),
    )
    runtime = RuntimeOptions(
        headless=env_bool("RUNNER_HEADLESS", True),
        slow_mo_ms=int(os.getenv("RUNNER_SLOW_MO_MS", "0")),
        timeout_ms=int(os.getenv("RUNNER_TIMEOUT_MS", "30000")),
    )

    return RunnerSettings(
        data_root=data_root,
        jobs_dir=jobs_dir,
        artifacts_dir=artifacts_dir,
        api_key=require_env("RUNNER_API_KEY"),
        default_credentials=credentials,
        default_guide_defaults=defaults,
        default_runtime=runtime,
        max_workers=int(os.getenv("RUNNER_MAX_WORKERS", "1")),
    )
