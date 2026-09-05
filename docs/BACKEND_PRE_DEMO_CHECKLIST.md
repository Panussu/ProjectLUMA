# Backend pre-demo checklist

Use this checklist on PC 3 before the three-computer classroom demonstration. Do not store completed secrets or passwords in this repository.

## 1. Prepare PC 3

- Install Python 3.11 or newer and confirm `python --version` works.
- Connect PC 3 to the same trusted VLAN as PC 1 and PC 2.
- Run `ipconfig` and record PC 3's actual IPv4 address.
- Run `./scripts/run-backend.ps1 -Vlan` once to create `backend/.venv` and `backend/.env`.
- Edit `backend/.env` before starting again.

Required environment values:

- `SECRET_KEY`: unique random value of at least 32 characters.
- `JWT_SECRET_KEY`: a different random value of at least 32 characters.
- `AI_SERVICE_TOKEN`: the exact shared token configured on PC 1.
- `AI_SERVICE_URL`: PC 1's actual address, for example `http://192.168.1.30:8000`.
- `CORS_ORIGINS`: PC 2's browser origin, for example `http://192.168.1.10`.
- `FLASK_DEBUG=0` and `DEPLOYMENT_MODE=vlan`.

Allow inbound TCP port 5000 from PC 2 only. Do not expose the SQLite database, media directory, or PC 1 service token through a shared folder.

## 2. Start and verify

Start WebUI Forge and the LUMA AI wrapper on PC 1 first. On PC 3, run:

```powershell
./scripts/run-backend.ps1
```

In another terminal on PC 3, run:

```powershell
./scripts/check-backend.ps1
```

The expected result is `Backend=ok`, `Database=ok`, and `AiService=ok`. From PC 2, confirm `Test-NetConnection <PC3-IP> -Port 5000` succeeds.

## 3. Acceptance flow

- Register a new account through PC 2.
- Log in and confirm `/api/v1/auth/me` returns the same user.
- Submit one generation and one edit job.
- Observe `queued`, `processing`, then `completed`.
- Download each result using its signed URL.
- Confirm a second account cannot read the first account's job or media.
- Stop PC 1 and confirm Backend remains reachable while `ai_service` becomes `unavailable`.
- Submit a job while AI is unavailable and confirm it becomes `failed` with a safe message.
- Restart PC 1 and confirm a new job completes.
- Restart Backend and confirm no job remains indefinitely in `processing`.

Record the date, tester, actual IP addresses, job IDs, and screenshots or command output. The deployment is not accepted until these checks have been performed on the real PCs.

## 4. Backup and storage

Stop new job submissions, then create a backup:

```powershell
./scripts/backup-backend.ps1
```

Confirm the new backup contains `luma.db`, `media/`, and `manifest.json`. Preview retention cleanup without changing data:

```powershell
./scripts/cleanup-backend.ps1
```

Use `-Apply` only after a backup and after reviewing the candidate count.

## 5. Automated tests

From the repository root:

```powershell
./backend/.venv/Scripts/pip.exe install -r requirements-dev.txt
./backend/.venv/Scripts/python.exe -m pytest
```

All tests must pass before merging this branch into `main`.
