# Project LUMA

LUMA (Learning-based Universal Media Artist) is a distributed web application for creating and editing images through an AI service. The project is designed for a small team and can run across three computers on the same local network.

## Architecture

| Computer | Default address | Responsibilities |
| --- | --- | --- |
| Frontend | `192.168.1.10` | Nginx reverse proxy and static HTML/CSS/JavaScript |
| Backend | `192.168.1.20` | Flask API, authentication, job queue, image storage, and database |
| AI server | `192.168.1.30` | Image generation and editing service |

All addresses and ports are configurable. For local development, every service can run on one computer.

```text
Browser
   |
   v
Nginx :80
   |-- /                 -> static frontend
   |-- /api/             -> Flask backend :5000
   |-- /media/           -> Flask backend :5000
   `-- /health           -> Flask backend :5000
                              |
                              `-- AI service :8000
```

SQLite is the default database because it needs no separate database computer. PostgreSQL can be selected later through `DATABASE_URL` without changing the API.

## Repository layout

```text
frontend/       Browser interface
backend/        Flask API, authentication, database, and jobs
ai-engine/      Replaceable image-generation/editing service
nginx/          Reverse-proxy configuration
docs/           Architecture, API contract, and deployment guides
scripts/        PowerShell development scripts
tests/          Integration checks
```

## Shared API contract

The browser calls only Nginx using same-origin URLs beginning with `/api/v1`. It must not call the Flask or AI computer directly.

| Method and path | Authentication | Purpose |
| --- | --- | --- |
| `GET /api/v1/health` | No | Backend and dependency health |
| `POST /api/v1/auth/register` | No | Create a user account |
| `POST /api/v1/auth/login` | No | Obtain an access token |
| `GET /api/v1/auth/me` | Bearer token | Read the current user |
| `POST /api/v1/jobs/generate` | Bearer token | Queue image generation |
| `POST /api/v1/jobs/edit` | Bearer token | Upload and queue an image edit |
| `GET /api/v1/jobs` | Bearer token | List the current user's jobs |
| `GET /api/v1/jobs/{id}` | Bearer token | Read progress or result |
| `GET /media/{filename}` | Bearer token or signed URL | Download a result image |

Generation and editing are asynchronous. A successful `POST` returns HTTP `202` and a job with status `queued`. The frontend polls `GET /api/v1/jobs/{id}` until its status becomes `completed` or `failed`.

The AI service is private and called only by the backend:

| Method and path | Purpose |
| --- | --- |
| `GET /health` | AI service health |
| `POST /v1/generate` | Generate an image |
| `POST /v1/edit` | Edit an uploaded image |

See [docs/API_CONTRACT.md](docs/API_CONTRACT.md) for request and response examples, ownership rules, limits, and error behavior.

## Quick start on one computer

Requirements: Python 3.11 or newer. Nginx is optional for local development.

1. Copy each environment example.

   ```powershell
   Copy-Item backend/.env.example backend/.env
   Copy-Item ai-engine/.env.example ai-engine/.env
   ```

2. In Stability Matrix, launch Stable Diffusion WebUI Forge with `--api --port 7860`. For testing without Forge, change `AI_PROVIDER` in `ai-engine/.env` to `development-procedural`.

3. Start the LUMA AI wrapper, backend, and frontend in separate PowerShell terminals.

   ```powershell
   ./scripts/run-ai.ps1
   ./scripts/run-backend.ps1
   ./scripts/run-frontend.ps1
   ```

4. Open `http://localhost:8080`.

For local development, the frontend development server sends API requests to `http://localhost:5000`. In the deployed system, Nginx provides one public origin and forwards the requests.

## Docker quick start

```powershell
docker compose up --build
```

Open `http://localhost`. Runtime data is stored in Docker volumes.

## Three-computer deployment

1. Give each computer a stable LAN address or DHCP reservation.
2. Run the frontend and Nginx on `192.168.1.10`.
3. Run the Flask backend on `192.168.1.20:5000`.
4. Run the AI service on `192.168.1.30:8000`.
5. Allow only the required ports through each computer's firewall.
6. Change `SECRET_KEY`, `JWT_SECRET_KEY`, and `AI_SERVICE_TOKEN` before deployment.
7. Test the complete browser-to-AI flow from a different computer.

Detailed steps are in [docs/DEPLOYMENT.md](docs/DEPLOYMENT.md).

## Branch ownership

The remote repository contains `Frontend`, `Backend`, `AiEngine`, `Routing`, and `QA` branches. `main` is the integration branch and contains the shared API contract. Feature work should be committed in small, focused commits and merged into `main` only after its tests pass.

## Current AI provider

The normal provider is Stable Diffusion WebUI Forge installed and launched through Stability Matrix. The LUMA AI wrapper converts the stable `/v1/generate` and `/v1/edit` contract into Forge `/sdapi/v1/txt2img` and `/sdapi/v1/img2img` requests.

The private AI wrapper uses FastAPI and runs with Uvicorn on port 8000. Its interactive API documentation is available at `http://127.0.0.1:8000/docs` on the AI computer. The main user API, authentication, jobs, and SQLite database remain in the Flask backend on port 5000.

A lightweight procedural provider remains available for development, automated tests, and Docker demonstrations without a GPU. It is not a trained generative model and must not be presented as one.

## Security notes

- Do not commit `.env` files, tokens, passwords, databases, uploads, or generated images.
- The backend limits upload size and validates image types.
- The AI service requires a shared service token.
- Use HTTPS when the application leaves a trusted classroom LAN.
