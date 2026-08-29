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

Copy `ai-engine`, create its `.env`, set `HOST=0.0.0.0`, and start it with `scripts/run-ai.ps1`. Allow inbound TCP port 8000 only from the backend computer.

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
6. Stop the AI service and confirm health reports it as unavailable.
7. Restart the AI service and retry.

## Database choice

SQLite is appropriate for the classroom demonstration and a single Flask process. For multiple backend processes or heavier use, install PostgreSQL and its driver, create a restricted database user, and set a PostgreSQL SQLAlchemy URL. Back up both the database and result images.

## Operational checks

- Backend and dependency health
- Nginx access and error logs
- Backend application logs
- Free disk space for images
- Failed job count and messages
- Database and media restore test

