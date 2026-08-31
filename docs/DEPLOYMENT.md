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

## Three-computer same-VLAN deployment

This is the required classroom profile:

| Computer | Proposed address | Service |
| --- | --- | --- |
| PC 1 | `192.168.1.30` | WebUI Forge on localhost plus FastAPI on port 8000 |
| PC 2 | `192.168.1.10` | Static frontend and Nginx on port 80 |
| PC 3 | `192.168.1.20` | Flask on port 5000 plus local SQLite storage |

The addresses are examples. All three PCs must be connected to the same VLAN, and their actual addresses must replace these values before the demonstration. Tailscale, public IP addresses, and router port forwarding are not used in this profile.

### 1. Confirm the network

Connect every PC to the same classroom VLAN. Run `ipconfig` on each one and reserve each address in the router or VLAN DHCP server when possible. Check for wireless client isolation if computers on the same Wi-Fi cannot reach each other.

From PC 2, test PC 3. From PC 3, test PC 1:

```powershell
# Run on PC 2
Test-NetConnection 192.168.1.20 -Port 5000

# Run on PC 3 after FastAPI is started
Test-NetConnection 192.168.1.30 -Port 8000
```

### 2. AI computer

Install Stability Matrix, then use it to install the Stable Diffusion WebUI Forge package and the required checkpoint model.

In the Forge package launch options, add:

```text
--api --port 7860
```

Do not add `--listen` when Forge and the LUMA AI wrapper run on the same computer. This keeps the unwrapped Forge API private on `127.0.0.1`. After launching Forge, open `http://127.0.0.1:7860/docs` on the AI computer and confirm that `/sdapi/v1/txt2img` and `/sdapi/v1/img2img` are present.

On PC 1, copy the prepared VLAN environment file:

```powershell
Set-Location C:\ProjectLUMA
Copy-Item ai-engine\.env.vlan.example ai-engine\.env
notepad ai-engine\.env
```

Set a long `AI_SERVICE_TOKEN`. The same token will be copied to PC 3. `HOST=0.0.0.0` makes FastAPI reachable on the VLAN, while `FORGE_URL=http://127.0.0.1:7860` keeps Forge local to PC 1. `FORGE_CHECKPOINT` can remain empty to use the model selected in Forge.

Start FastAPI with `scripts/run-ai.ps1`. Open `http://127.0.0.1:8000/docs` locally to inspect its API. Allow inbound TCP port 8000 only from PC 3. Do not open Forge port 7860 in Windows Firewall.

### 3. Backend computer

On PC 3, copy and edit the Flask VLAN environment file:

```powershell
Set-Location C:\ProjectLUMA
Copy-Item backend\.env.vlan.example backend\.env
notepad backend\.env
```

Set `AI_SERVICE_URL=http://192.168.1.30:8000`, and copy the exact `AI_SERVICE_TOKEN` from PC 1. Change `SECRET_KEY` and `JWT_SECRET_KEY`. Leave `DATABASE_URL` unset so SQLite is created under `backend/data` on PC 3. Start Flask with `scripts/run-backend.ps1` and allow inbound TCP port 5000 only from PC 2.

### 4. Frontend computer

On PC 2, install Nginx and keep the repository at `C:\ProjectLUMA`. In `nginx/luma.conf`, set the upstream to PC 3's actual VLAN address and set `server_name` to PC 2's address. The proposed values are already present:

```nginx
upstream luma_backend {
    server 192.168.1.20:5000;
}

server {
    listen 80;
    server_name 192.168.1.10 localhost;
    root C:/ProjectLUMA/frontend;
}
```

Copy `nginx/nginx.conf` and `nginx/luma.conf` into the Nginx `conf` directory, or adapt their include paths to the repository. Test and start Nginx:

```powershell
nginx.exe -t
nginx.exe
```

Allow inbound TCP port 80 from the classroom VLAN. The browser communicates only with PC 2; Nginx forwards `/api` and `/media` to Flask on PC 3.

### 5. End-to-end validation

1. Open `http://192.168.1.10`.
2. Register a new account.
3. Submit a generation prompt.
4. Confirm the job moves through `queued`, `processing`, and `completed`.
5. Confirm the result image appears and is present on the backend computer.
6. Stop Forge and confirm the LUMA health endpoint reports the AI provider as unavailable.
7. Restart Forge and retry.

Start services in this order: Forge on PC 1, FastAPI on PC 1, Flask on PC 3, and finally Nginx on PC 2.

## Database choice

SQLite is appropriate for the classroom demonstration and a single Flask process. For multiple backend processes or heavier use, install PostgreSQL and its driver, create a restricted database user, and set a PostgreSQL SQLAlchemy URL. Back up both the database and result images.

## Operational checks

- Backend and dependency health
- Nginx access and error logs
- Backend application logs
- Free disk space for images
- Failed job count and messages
- Database and media restore test

