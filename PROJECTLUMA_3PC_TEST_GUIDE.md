# ProjectLUMA Three-PC Test Guide

This guide explains how to run and test ProjectLUMA on three Windows computers connected to the same trusted VLAN.

## 1. System layout

| Computer | Proposed address | Owner and services |
| --- | --- | --- |
| PC 1 | `192.168.1.30` | AI Engineer: Stability Matrix, WebUI Forge, FastAPI wrapper |
| PC 2 | `192.168.1.10` | Frontend/Routing: HTML, CSS, JavaScript, Nginx |
| PC 3 | `192.168.1.20` | Backend: Flask, job queue, SQLite, uploaded and generated files |

The addresses above are examples. Run `ipconfig` on every computer and replace the examples with the actual VLAN addresses.

```text
Browser
   |
   v
PC 2: Nginx + Frontend :80
   |
   v
PC 3: Flask + SQLite :5000
   |
   v
PC 1: FastAPI :8000
   |
   v
PC 1: WebUI Forge 127.0.0.1:7860
```

Tailscale, public IP addresses, and router port forwarding are not required. The three PCs must be able to communicate inside the same VLAN.

## 2. Requirements

Install the following software:

- All PCs: Git and Python 3.11 or newer
- PC 1: Stability Matrix and Stable Diffusion WebUI Forge
- PC 2: Nginx for Windows
- PC 3: No separate database program is needed because the project uses SQLite

## 3. Download the project on all PCs

Run on PC 1, PC 2, and PC 3:

```powershell
Set-Location C:\
git clone https://github.com/Panussu/ProjectLUMA.git
Set-Location C:\ProjectLUMA
git checkout main
git pull origin main
```

If `C:\ProjectLUMA` already exists:

```powershell
Set-Location C:\ProjectLUMA
git checkout main
git pull origin main
```

## 4. Record the VLAN addresses

Run this on each PC:

```powershell
ipconfig
```

Record the IPv4 address:

| Computer | Actual IPv4 address |
| --- | --- |
| PC 1 | ____________________ |
| PC 2 | ____________________ |
| PC 3 | ____________________ |

If the addresses are not `192.168.1.30`, `192.168.1.10`, and `192.168.1.20`, update all examples in the following sections.

## 5. PC 1: WebUI Forge and FastAPI

### 5.1 Configure Forge

Use Stability Matrix to install WebUI Forge and a checkpoint model. Add these Forge launch arguments:

```text
--api --port 7860
```

Do not add `--listen`. Forge should stay private on PC 1.

Start Forge and open:

```text
http://127.0.0.1:7860/docs
```

Confirm these endpoints exist:

- `/sdapi/v1/txt2img`
- `/sdapi/v1/img2img`

### 5.2 Configure FastAPI

```powershell
Set-Location C:\ProjectLUMA
Copy-Item ai-engine\.env.vlan.example ai-engine\.env
notepad ai-engine\.env
```

Confirm these settings:

```dotenv
HOST=0.0.0.0
PORT=8000
AI_PROVIDER=forge
AI_SERVICE_TOKEN=replace-with-one-shared-long-random-service-token
FORGE_URL=http://127.0.0.1:7860
```

Generate a service token:

```powershell
[Convert]::ToHexString(
    [Security.Cryptography.RandomNumberGenerator]::GetBytes(32)
)
```

Paste the result into `AI_SERVICE_TOKEN`. PC 3 must use exactly the same token. Do not commit the `.env` file.

### 5.3 Open port 8000

Run PowerShell as Administrator. Replace `192.168.1.20` with PC 3's actual address:

```powershell
New-NetFirewallRule `
  -DisplayName "LUMA FastAPI 8000" `
  -Direction Inbound `
  -Protocol TCP `
  -LocalPort 8000 `
  -RemoteAddress 192.168.1.20 `
  -Action Allow
```

Do not open Forge port `7860` to the VLAN.

### 5.4 Start and test FastAPI

```powershell
Set-Location C:\ProjectLUMA
.\scripts\run-ai.ps1
```

Keep this terminal open. In another PowerShell window, run:

```powershell
Invoke-RestMethod http://127.0.0.1:8000/health
```

Expected values:

```text
status   : ok
service  : luma-ai
provider : forge
```

FastAPI documentation is available at:

```text
http://127.0.0.1:8000/docs
```

## 6. PC 3: Flask and SQLite

### 6.1 Test PC 1

Replace `192.168.1.30` with PC 1's actual address:

```powershell
Test-NetConnection 192.168.1.30 -Port 8000
Invoke-RestMethod http://192.168.1.30:8000/health
```

`TcpTestSucceeded` must be `True`.

### 6.2 Configure Flask

```powershell
Set-Location C:\ProjectLUMA
Copy-Item backend\.env.vlan.example backend\.env
notepad backend\.env
```

Confirm and update these settings:

```dotenv
HOST=0.0.0.0
PORT=5000

SECRET_KEY=replace-with-a-long-random-value
JWT_SECRET_KEY=replace-with-another-long-random-value

AI_SERVICE_URL=http://192.168.1.30:8000
AI_SERVICE_TOKEN=use-the-exact-token-from-PC1

CORS_ORIGINS=http://192.168.1.10
```

Use PC 1's actual address in `AI_SERVICE_URL` and PC 2's actual address in `CORS_ORIGINS`.

Generate separate values for `SECRET_KEY` and `JWT_SECRET_KEY` by running this command twice:

```powershell
[Convert]::ToHexString(
    [Security.Cryptography.RandomNumberGenerator]::GetBytes(32)
)
```

Leave `DATABASE_URL` unset. SQLite will be created automatically at:

```text
C:\ProjectLUMA\backend\data\luma.db
```

### 6.3 Open port 5000

Run PowerShell as Administrator. Replace `192.168.1.10` with PC 2's actual address:

```powershell
New-NetFirewallRule `
  -DisplayName "LUMA Flask 5000" `
  -Direction Inbound `
  -Protocol TCP `
  -LocalPort 5000 `
  -RemoteAddress 192.168.1.10 `
  -Action Allow
```

### 6.4 Start and test Flask

```powershell
Set-Location C:\ProjectLUMA
.\scripts\run-backend.ps1
```

Keep this terminal open. In another PowerShell window, run:

```powershell
Invoke-RestMethod http://127.0.0.1:5000/api/v1/health
```

## 7. PC 2: Frontend and Nginx

### 7.1 Test PC 3

Replace `192.168.1.20` with PC 3's actual address:

```powershell
Test-NetConnection 192.168.1.20 -Port 5000
Invoke-RestMethod http://192.168.1.20:5000/api/v1/health
```

`TcpTestSucceeded` must be `True`.

### 7.2 Configure Nginx

Open the routing configuration:

```powershell
notepad C:\ProjectLUMA\nginx\luma.conf
```

Set PC 3's address as the backend and PC 2's address as `server_name`:

```nginx
upstream luma_backend {
    server 192.168.1.20:5000;
    keepalive 16;
}

server {
    listen 80;
    server_name 192.168.1.10 localhost;

    root C:/ProjectLUMA/frontend;
    index index.html;
}
```

Keep the remaining locations and proxy settings from the existing `nginx/luma.conf` file.

If Nginx is installed at `C:\nginx`, copy the prepared configurations:

```powershell
Copy-Item C:\ProjectLUMA\nginx\nginx.conf C:\nginx\conf\nginx.conf -Force
Copy-Item C:\ProjectLUMA\nginx\luma.conf C:\nginx\conf\luma.conf -Force
```

### 7.3 Open port 80

Run PowerShell as Administrator. Change the subnet if the VLAN does not use `192.168.1.x`:

```powershell
New-NetFirewallRule `
  -DisplayName "LUMA Nginx 80" `
  -Direction Inbound `
  -Protocol TCP `
  -LocalPort 80 `
  -RemoteAddress 192.168.1.0/24 `
  -Action Allow
```

### 7.4 Start and test Nginx

```powershell
Set-Location C:\nginx
.\nginx.exe -t
.\nginx.exe
```

If Nginx is already running:

```powershell
.\nginx.exe -t
.\nginx.exe -s reload
```

Test the complete route through Nginx:

```powershell
Invoke-RestMethod http://127.0.0.1/health
```

## 8. End-to-end test

From any computer on the same VLAN, open PC 2's address:

```text
http://192.168.1.10
```

Complete these checks:

1. Register a new user.
2. Log in.
3. Enter an image-generation prompt.
4. Submit the job.
5. Confirm the job changes from `queued` to `processing` and then `completed`.
6. Confirm the generated image appears.
7. Download the generated image.
8. Confirm `backend/data/luma.db` exists on PC 3.
9. Confirm generated images are stored on PC 3.
10. Stop Forge and confirm the application reports that the AI provider is unavailable.
11. Restart Forge and retry generation.

## 9. Startup order

Always start the system in this order:

1. PC 1: WebUI Forge
2. PC 1: FastAPI wrapper
3. PC 3: Flask backend
4. PC 2: Nginx
5. Open the website in a browser

## 10. Connection checklist

| Source | Destination | Test |
| --- | --- | --- |
| PC 1 | Local Forge | `http://127.0.0.1:7860/docs` |
| PC 1 | Local FastAPI | `http://127.0.0.1:8000/health` |
| PC 3 | PC 1 FastAPI | `Test-NetConnection PC1-IP -Port 8000` |
| PC 3 | Local Flask | `http://127.0.0.1:5000/api/v1/health` |
| PC 2 | PC 3 Flask | `Test-NetConnection PC3-IP -Port 5000` |
| PC 2 | Local Nginx | `http://127.0.0.1/health` |
| VLAN browser | PC 2 Nginx | `http://PC2-IP` |

## 11. Common problems

### `TcpTestSucceeded` is `False`

- Check the destination computer's IPv4 address.
- Confirm the service is running.
- Confirm `HOST=0.0.0.0` for FastAPI and Flask.
- Check Windows Firewall.
- Check whether the Wi-Fi has client isolation enabled.

### FastAPI health reports Forge unavailable

- Start Forge before FastAPI.
- Confirm Forge uses `--api --port 7860`.
- Confirm `FORGE_URL=http://127.0.0.1:7860`.
- Confirm Forge has loaded a checkpoint model.

### Flask cannot call FastAPI

- Confirm `AI_SERVICE_URL` uses PC 1's address and port `8000`.
- Confirm PC 1 and PC 3 use the exact same `AI_SERVICE_TOKEN`.
- Test port `8000` from PC 3.

### Nginx shows a gateway error

- Confirm Flask is running on PC 3.
- Confirm the Nginx upstream uses PC 3's address and port `5000`.
- Run `nginx.exe -t` and inspect `C:\nginx\logs\error.log`.

### The website opens but generation fails

- Check the health endpoint through Nginx.
- Check the Flask terminal on PC 3.
- Check the FastAPI terminal on PC 1.
- Check Forge on PC 1.
- Confirm the shared service token matches.

## 12. Files that must remain private

Do not send or commit these runtime files:

- `ai-engine/.env`
- `backend/.env`
- `backend/data/luma.db`
- Uploaded user images
- Generated result images containing private data

The `.env.vlan.example` files are safe templates. Replace their placeholder secrets only inside the untracked `.env` files on each computer.
