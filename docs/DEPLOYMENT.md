# Deployment Guide

## Configuration

Never commit real secrets. Create `.env` files from the examples and change at least `SECRET_KEY`, `JWT_SECRET_KEY`, and `AI_SERVICE_TOKEN`. The AI token must match on the backend and AI computers.

## Local development

Run the scripts from the repository root in separate PowerShell terminals:

```powershell
./scripts/run-ai.ps1
./scripts/run-backend.ps1
./scripts/run-frontend.ps1
```

The scripts create isolated virtual environments inside each service directory and install the pinned requirements.

## Three-computer deployment

### 1. Confirm the network

Run `ipconfig` on every computer and reserve each address in the router when possible. Verify connectivity with `Test-NetConnection`.

```powershell
Test-NetConnection 192.168.1.20 -Port 5000
Test-NetConnection 192.168.1.30 -Port 8000
```

### 2. AI computer

Install Stability Matrix, then use it to install the Stable Diffusion WebUI Forge package and the required checkpoint model.

In the Forge package launch options, add:

```text
--api --port 7860
```

Do not add `--listen` when Forge and the LUMA AI wrapper run on the same computer. This keeps the unwrapped Forge API private on `127.0.0.1`. After launching Forge, open `http://127.0.0.1:7860/docs` on the AI computer and confirm that `/sdapi/v1/txt2img` and `/sdapi/v1/img2img` are present.

Copy `ai-engine`, create its `.env`, and set:

```text
HOST=0.0.0.0
PORT=8000
AI_PROVIDER=forge
FORGE_URL=http://127.0.0.1:7860
FORGE_CHECKPOINT=the-exact-checkpoint-name-shown-in-Forge
```

The `FORGE_CHECKPOINT` setting can remain empty to use the model currently selected in Forge. Start the FastAPI wrapper with `scripts/run-ai.ps1`; the script launches Uvicorn through `ai-engine/app.py`. Open `http://127.0.0.1:8000/docs` locally to inspect its API. Allow inbound TCP port 8000 only from the backend computer. Do not open Forge port 7860 in Windows Firewall.

### 3. Backend computer

Copy `backend`, create its `.env`, set `HOST=0.0.0.0`, and set `AI_SERVICE_URL=http://192.168.1.30:8000`. Start it with `scripts/run-backend.ps1`. Allow inbound TCP port 5000 only from the Nginx computer.

### 4. Frontend computer

Install Nginx, copy `frontend` to its static web root, and adapt the paths in `nginx/luma.conf`. Confirm the backend address, then reload Nginx.

### 5. End-to-end validation

1. Open `http://192.168.1.10`.
2. Register a new account.
3. Submit a generation prompt.
4. Confirm the job moves through `queued`, `processing`, and `completed`.
5. Confirm the result image appears and is present on the backend computer.
6. Stop Forge and confirm the LUMA health endpoint reports the AI provider as unavailable.
7. Restart Forge and retry.

## Database choice

SQLite is appropriate for the classroom demonstration and a single Flask process. For multiple backend processes or heavier use, install PostgreSQL and its driver, create a restricted database user, and set a PostgreSQL SQLAlchemy URL. Back up both the database and result images.

## Operational checks

- Backend and dependency health
- Nginx access and error logs
- Backend application logs
- Free disk space for images
- Failed job count and messages
- Database and media restore test

