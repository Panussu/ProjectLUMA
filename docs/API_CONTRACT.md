# LUMA API Contract

API version: `v1`

## General rules

- Browser base path: `/api/v1`
- JSON requests use `Content-Type: application/json`.
- Protected endpoints use `Authorization: Bearer <token>`.
- Dates use UTC ISO 8601 strings.
- Errors always include an `error` object with `code` and `message`.
- Unknown JSON fields may be ignored, but required fields must be present.
- Maximum request size defaults to 16 MiB.

Example error:

```json
{
  "error": {
    "code": "validation_error",
    "message": "Prompt must contain between 3 and 1000 characters."
  }
}
```

## Authentication

### Register

`POST /api/v1/auth/register`

```json
{
  "username": "student1",
  "password": "a-password-with-at-least-8-characters"
}
```

Success: HTTP `201` with the same response shape as login. Usernames are case-insensitive and must be 3-40 characters using letters, numbers, `_`, `.`, or `-`.

### Login

`POST /api/v1/auth/login`

```json
{
  "username": "student1",
  "password": "a-password-with-at-least-8-characters"
}
```

Success: HTTP `200`.

```json
{
  "access_token": "token",
  "user": {
    "id": 1,
    "username": "student1"
  }
}
```

### Current user

`GET /api/v1/auth/me`

Success: HTTP `200` with a `user` object.

## Jobs

Job statuses are `queued`, `processing`, `completed`, or `failed`. Job types are `generate` and `edit`.

### Generate an image

`POST /api/v1/jobs/generate`

```json
{
  "prompt": "A small robot painting flowers in a bright studio",
  "negative_prompt": "blurry, text",
  "width": 768,
  "height": 768,
  "seed": 42,
  "steps": 20
}
```

Constraints:

- `prompt`: 3-1000 characters
- `negative_prompt`: 0-1000 characters
- `width`, `height`: 256-1024 and divisible by 64
- `steps`: 1-50
- `seed`: optional integer from 0 to 4,294,967,295

Success: HTTP `202` with a job object whose initial status is `queued`.

### Edit an image

`POST /api/v1/jobs/edit` uses `multipart/form-data`.

| Field | Required | Description |
| --- | --- | --- |
| `image` | Yes | PNG, JPEG, or WebP image |
| `prompt` | Yes | Editing instruction, 3-1000 characters |
| `strength` | No | Number from 0 to 1; default `0.65` |
| `seed` | No | Integer from 0 to 4,294,967,295 |

Success: HTTP `202` with a job object.

### List jobs

`GET /api/v1/jobs?limit=20`

Success: HTTP `200` with `jobs` and `count` fields. The maximum `limit` is 100.

### Read one job

`GET /api/v1/jobs/{id}`

Only the job owner can read it. Completed jobs include a same-origin `result_url` under `/media/`.

## Health

`GET /api/v1/health`

HTTP `200` means Flask and the database are available. The response reports the AI dependency separately so operators can distinguish a complete outage from an unavailable model server.

## Private AI API

Every request except `GET /health` sends `X-LUMA-Service-Token`. The service returns an image file with metadata in response headers.

### Generate

`POST /v1/generate` uses JSON with the same generation fields as the public endpoint.

### Edit

`POST /v1/edit` uses multipart form data with `image`, `prompt`, `strength`, and `seed`.

## Ownership checklist

Before LAN integration, all contributors must agree on:

- Actual computer addresses and listening ports
- Whether Windows Firewall permits the required inbound connections
- The final frontend origin
- Maximum input and output image sizes
- Expected maximum generation duration
- Polling interval and whether WebSockets will be added
- Shared AI service token distribution
- SQLite or PostgreSQL for the final demonstration
- Backup location and retention period

