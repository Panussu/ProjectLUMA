# LUMA Architecture

## Decisions

- Start with three computers.
- Run all three computers on the same trusted classroom VLAN for the demonstration.
- Keep all IP addresses, ports, and secrets in environment variables.
- Use SQLite on the backend computer for the first working version.
- Allow PostgreSQL through the same SQLAlchemy database interface.
- Keep the AI service private. The browser never connects to it directly.
- Use asynchronous jobs because image generation can take longer than normal HTTP proxy timeouts.
- Poll for job status in the first version. A WebSocket channel can be added later without changing job creation.

## Responsibilities

### Frontend and routing

- Present registration, login, image generation, image editing, history, and errors.
- Use relative `/api/v1` and `/media` addresses in deployed mode.
- Serve static files through Nginx.
- Forward API and media requests to Flask.
- Add forwarded headers, body-size limits, and appropriate timeouts.

### Backend

- Own users, password hashes, tokens, jobs, metadata, logs, and stored files.
- Validate requests before sending work to the AI service.
- Keep users isolated so one user cannot read another user's jobs.
- Translate AI-service failures into stable API errors.
- Persist job state in the database.

### AI engine

- Run Stable Diffusion WebUI Forge through Stability Matrix on the AI computer.
- Keep Forge on `127.0.0.1:7860` and enable its API with `--api`.
- Run the authenticated FastAPI LUMA wrapper with Uvicorn on port 8000 for the backend computer.
- Use the wrapper's `/docs` and `/openapi.json` pages while developing or testing the AI integration.
- Translate LUMA generation and editing requests into Forge API requests.
- Return a result file and useful metadata to the backend.
- Avoid owning user accounts or browser sessions.
- Expose a health endpoint for integration tests.

### QA and operations

- Test each service independently and then test through Nginx.
- Back up the database and result directory together.
- Monitor health, job failures, disk space, and response times.
- Never report an AI generation as successful until a result file is readable.

## Deployment profiles

### Local development

| Service | Address |
| --- | --- |
| Frontend | `http://localhost:8080` |
| Backend | `http://localhost:5000` |
| LUMA AI wrapper | `http://localhost:8000` |
| WebUI Forge | `http://127.0.0.1:7860` |

### Three-computer classroom VLAN

| Service | Address |
| --- | --- |
| Browser entry point | `http://192.168.1.10` |
| Backend, reachable from Nginx | `http://192.168.1.20:5000` |
| LUMA AI wrapper, reachable from backend | `http://192.168.1.30:8000` |
| WebUI Forge, local to AI computer | `http://127.0.0.1:7860` |

These are proposed defaults, not hard-coded requirements. Confirm the addresses with `ipconfig` on each computer before deployment. The three PCs must be able to reach one another on the same VLAN; no VPN, public IP address, or router port forwarding is required.

## Data flow

1. The user signs in through the frontend.
2. Flask verifies the credentials and returns a short-lived bearer token.
3. The user submits a prompt or an image edit.
4. Flask validates the request, stores a `queued` job, and returns HTTP `202`.
5. A backend worker changes the job to `processing` and calls the private AI service.
6. The FastAPI LUMA wrapper calls Forge, decodes its result, and sends the image back to Flask.
7. Flask stores the result, marks the job `completed`, and exposes its metadata.
8. The frontend polls the job endpoint and displays the finished image.

## Production growth path

The first version deliberately stays small. If usage grows, replace the in-process worker with Redis and Celery/RQ, move files to object storage, use PostgreSQL, and add HTTPS. These are deployment changes; the public API can remain stable.

