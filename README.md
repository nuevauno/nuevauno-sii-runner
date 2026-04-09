# NUEVAUNO SII Runner

Multi-tenant SII execution service for `KODO SII`.

## What this service does

- exposes a small HTTP API for dispatch-guide automation jobs
- runs Playwright against the Chilean SII portal
- saves artifacts and final PDFs to persistent storage
- renames final PDFs with the real folio emitted by SII
- is designed to run as a Coolify-managed container

## Current scope

Current production scope:

- `dispatch_guides`

Planned next scopes:

- `boleta`
- `factura`
- `factura_exenta`
- `nota_credito`
- `nota_debito`

## API

### Health

`GET /health`

### Create dispatch-guide job

`POST /v1/dispatch-guides/jobs`

Example body:

```json
{
  "tenant_id": "tn_rng",
  "job_name": "2026-04-07-batch",
  "guides": [
    {
      "issue_date": "2026-04-07",
      "note_label": "Guia 1",
      "auto_units": 63,
      "bus_units": 6
    }
  ]
}
```

### Get job

`GET /v1/jobs/{job_id}`

All `/v1/*` endpoints require the `X-Runner-Key` header with the value from `RUNNER_API_KEY`.

## Environment

The service can receive tenant-specific overrides in the request body, but it also supports default env-backed values so it can run immediately for the current client.

Required runtime env for the current setup:

- `RUNNER_API_KEY`
- `SII_RUNNER_HOST`
- `SII_LOGIN_URL`
- `SII_TARGET_MENU_URL`
- `SII_USERNAME_RUT`
- `SII_PASSWORD`
- `SII_CERTIFICATE_PASSWORD`
- `SII_SELLER_NAME`
- `SII_RECIPIENT_NAME`
- `SII_RECIPIENT_RUT`
- `SII_RECIPIENT_BUSINESS`
- `SII_RECIPIENT_ADDRESS`
- `SII_RECIPIENT_CITY`
- `SII_RECIPIENT_COMMUNE`
- `SII_TRANSFER_TYPE`
- `SII_TRANSPORTER_RUT`
- `SII_VEHICLE_PATENT`
- `SII_DRIVER_RUT`
- `SII_DRIVER_NAME`
- `SII_AUTO_DESCRIPTION`
- `SII_BUS_DESCRIPTION`
- `SII_REFERENCE_PREFIX`

Optional env:

- `RUNNER_DATA_ROOT` default `/data/kodo-sii`
- `RUNNER_HEADLESS` default `true`
- `RUNNER_TIMEOUT_MS` default `30000`
- `RUNNER_SLOW_MO_MS` default `0`
- `RUNNER_MAX_WORKERS` default `1`
- `RUNNER_HOST_PORT` default `18080`

## Local run

Use Python `3.12` or `3.13` locally. Current `pydantic-core` builds are not reliable on Python `3.14` yet.

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/python -m playwright install chromium
.venv/bin/uvicorn sii_runner.main:app --host 0.0.0.0 --port 8080
```

## Docker

Build:

```bash
docker build -t nuevauno-sii-runner .
```

Run:

```bash
docker run --rm -p 8080:8080 --env-file .env -v $(pwd)/data:/data nuevauno-sii-runner
```

## Coolify

Deploy this repo as a Docker Compose application using [compose.yaml](/Users/ahorasoyfelipe/Work/nuevauno/nuevauno-sii-runner/compose.yaml).
The compose file is already written so Coolify can detect and manage the required environment variables from the dashboard.

## Release and deploy

This repo is intended to follow the Nuevauno release pattern:

1. merge validated changes into `main`
2. publish a GitHub release tag in `YYYY.MM.DD` or `YYYY.MM.DD.N` format
3. GitHub Actions syncs the tagged source into the existing Coolify service path
4. the workflow rebuilds and restarts the Coolify-managed service in place
5. the public healthcheck is verified after deploy

The deploy workflow is in [.github/workflows/deploy.yml](/Users/ahorasoyfelipe/Work/nuevauno/nuevauno-sii-runner/.github/workflows/deploy.yml) and expects these GitHub repository secrets:

- `VPS_DEPLOY_HOST`
- `VPS_DEPLOY_PORT`
- `VPS_DEPLOY_USER`
- `VPS_DEPLOY_SSH_KEY`
- `COOLIFY_SII_RUNNER_PATH`
- `SII_RUNNER_HEALTHCHECK_URL`

Current production values for this service:

- `COOLIFY_SII_RUNNER_PATH=/data/coolify/services/ibfuvhj3ogi3pskkqh0fk6l7`
- `SII_RUNNER_HEALTHCHECK_URL=https://sii-runner.nuevauno.com/health`

Important operational note:

- the service remains visible and managed in Coolify
- the workflow redeploys the existing Coolify service instead of bypassing it with a separate process manager
