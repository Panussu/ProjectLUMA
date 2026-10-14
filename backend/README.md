# LUMA Backend

Flask owns authentication, users, jobs, database records, uploaded images and private results. Updated 14 October 2026 for the integrated `main` revision `5b52b9e`.

## Development

Run these commands inside `backend`:

```powershell
python -m venv .venv
./.venv/Scripts/python.exe -m pip install -r requirements.txt
if (-not (Test-Path .env)) { Copy-Item .env.example .env }
```

Edit `.env`, then start:

```powershell
./.venv/Scripts/python.exe run.py
```

The native server defaults to `127.0.0.1:5000`. From the repository root, `./scripts/run-backend.ps1` prepares the environment and starts the service. Preserve existing configuration when using example files.

## Configuration

| Setting | Purpose/default |
| --- | --- |
| `SECRET_KEY`, `JWT_SECRET_KEY` | Separate random secrets, at least 32 characters; replace example values |
| `AI_SERVICE_URL` | `http://127.0.0.1:8000` |
| `AI_SERVICE_TOKEN` | Random shared credential matching AI Engine; separate from user JWTs |
| `DATABASE_URL` | SQLite under `backend/data/luma.db`; configurable database connection |
| `MEDIA_ROOT` | `backend/media` |
| `UPLOAD_ROOT` | `backend/data/uploads` |
| `MAX_CONTENT_LENGTH` | 16 MiB |
| `CORS_ORIGINS` | Comma-separated origins; default `http://localhost:8080` |
| `MEDIA_TOKEN_MAX_AGE` | Signed media lifetime, 3600 seconds |
| `JWT_HOURS` | Token lifetime, 8 hours |
| `RECOVER_JOBS_ON_STARTUP` | Disabled natively; enabled by production Compose |
| `DEPLOYMENT_MODE` | `development`, `vlan` or `production`; deployment modes validate configuration |

Example/public signing secrets are rejected for private signed media even in development. Never commit credentials. The health endpoint can report a healthy database while the AI dependency is unavailable; inspect its dependency information.

## Requests, ownership and reliability

All routes below use the `/api/v1` prefix:

| Routes | Behavior |
| --- | --- |
| `/health`, `/register`, `/login` | Public health and authentication |
| `/me` | JWT-authenticated account |
| `/generate`, `/edit` | JWT-authenticated jobs; HTTP 202 |
| `/jobs` and individual job routes | Owner-scoped listing, status, progress and cancellation |
| `/interrupt`, `/skip` | Require authentication and an owned job ID; skip applies to processing jobs |
| `/prompts/favorites` and individual favorite routes | Owner-scoped create, search, read, update and delete |

Catalog and image utilities have separate endpoint contracts; see the [API contract](../docs/API_CONTRACT.md). Do not assume every proxy route has the same authentication requirements.

Backend sends `X-LUMA-Service-Token` and `X-LUMA-Job-ID` to AI Engine. Private images require the owner's JWT or a validated signed URL. Signed token payloads are validated, and media query tokens are excluded from application/Nginx request logs.

Generation dimensions must be 256–1024 pixels in multiples of 64, with 1–50 steps. Non-object request bodies and invalid editing options are rejected. CORS supports favorite update/delete requests. Abandoned results are cleaned up, and worker errors return safe messages.

The frontend polls active jobs approximately every second, keeps accepted jobs during temporary connection errors, and ignores responses from a previous login session. Logout clears private results and polling.

Jobs use an in-process thread pool. Run one backend process until a shared queue is introduced. Configure startup recovery to reconcile interrupted jobs after a restart.

## Deployment and storage

For a three-computer setup, Backend runs on PC 3, Nginx on PC 2 and AI Engine on PC 1. Start from `.env.vlan.example` only when creating a new configuration, then replace example IPs with verified addresses. Set the shared AI token and allow port 5000 from the frontend host. See the [three-PC guide](../docs/PROJECTLUMA_3PC_TEST_GUIDE.md).

Production Compose sets `DEPLOYMENT_MODE=production`, persists database/media/uploads, enables recovery and passes configured Forge connection settings to AI Engine. Set real secrets before starting it. See the [root README](../README.md) and [deployment guide](../docs/DEPLOYMENT.md).

SQLite is created automatically. Other databases require a suitable `DATABASE_URL` and driver; the bundled file backup/restore workflow supports SQLite.

## Backup, restore and cleanup

From the repository root:

```powershell
./scripts/backup.ps1 -BackupDir backups -RetentionDays 7
./scripts/restore.ps1
./scripts/cleanup-backend.ps1 -Days 30
```

Backup uses SQLite's backup API and configured storage paths. Restore selects the latest ZIP, requests confirmation, validates archive paths and database integrity, and preserves unrelated media. Stop all backend processes before restoring. Cleanup previews changes unless `-Apply` is supplied. The separate `backup-backend.ps1` directory backup is not an input for the ZIP restore command.

## Verification

From the repository root, install development dependencies into the interpreter used for testing:

```powershell
./backend/.venv/Scripts/python.exe -m pip install -r requirements-dev.txt
./backend/.venv/Scripts/python.exe -m pytest -q --tb=short
node --test tests/test_frontend.cjs
```

Current documentation verification reran **109 Python tests and 15 frontend tests**, all passing. The [latest audit](../docs/WEBAPP_AUDIT_2026-10-14.md) separately records 78 HTTP/API checks and 53 Chromium checks. Real Forge/GPU, container build/runtime and a physical three-PC deployment remain unverified. Older QA reports describe earlier revisions.
