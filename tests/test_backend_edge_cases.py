from __future__ import annotations

import io

import requests
from PIL import Image

import luma_backend
from luma_backend import worker


def authorization(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


class FailedAiResponse:
    status_code = 503
    ok = False
    content = b""
    text = "private provider details"
    headers: dict[str, str] = {}

    def json(self):
        return {"error": {"message": "private provider details"}}


def job_after_generate(backend_client, token: str) -> dict:
    created = backend_client.post(
        "/api/v1/jobs/generate",
        json={"prompt": "exercise a backend edge case"},
        headers=authorization(token),
    )
    assert created.status_code == 202
    job_id = created.get_json()["job"]["id"]
    return backend_client.get(
        f"/api/v1/jobs/{job_id}", headers=authorization(token)
    ).get_json()["job"]


def test_generate_rejects_fractional_dimension(backend_client, registered_user):
    response = backend_client.post(
        "/api/v1/jobs/generate",
        json={"prompt": "fractional dimensions", "width": 512.5, "height": 512},
        headers=authorization(registered_user["token"]),
    )
    assert response.status_code == 400
    assert response.get_json()["error"]["code"] == "validation_error"


def test_generate_rejects_non_string_prompt(backend_client, registered_user):
    response = backend_client.post(
        "/api/v1/jobs/generate",
        json={"prompt": 12345},
        headers=authorization(registered_user["token"]),
    )
    assert response.status_code == 400
    assert response.get_json()["error"]["message"] == "Prompt must be a string."


def test_edit_rejects_corrupt_image(backend_client, registered_user):
    response = backend_client.post(
        "/api/v1/jobs/edit",
        data={
            "prompt": "this is not an image",
            "image": (io.BytesIO(b"not-an-image"), "broken.png"),
        },
        headers=authorization(registered_user["token"]),
        content_type="multipart/form-data",
    )
    assert response.status_code == 400
    assert response.get_json()["error"]["code"] == "validation_error"


def test_edit_rejects_image_above_pixel_limit(backend_client, registered_user):
    buffer = io.BytesIO()
    Image.new("1", (2049, 2048)).save(buffer, format="PNG")
    buffer.seek(0)
    response = backend_client.post(
        "/api/v1/jobs/edit",
        data={
            "prompt": "oversized pixel dimensions",
            "image": (buffer, "oversized.png"),
        },
        headers=authorization(registered_user["token"]),
        content_type="multipart/form-data",
    )
    assert response.status_code == 400
    assert "too many pixels" in response.get_json()["error"]["message"]


def test_ai_http_failure_is_safe_and_marks_job_failed(
    backend_client, registered_user, monkeypatch
):
    monkeypatch.setattr(worker.requests, "post", lambda *args, **kwargs: FailedAiResponse())
    job = job_after_generate(backend_client, registered_user["token"])
    assert job["status"] == "failed"
    assert job["error"] == "AI service rejected the job (HTTP 503)."
    assert "private provider details" not in job["error"]


def test_ai_timeout_marks_job_failed(backend_client, registered_user, monkeypatch):
    def timeout(*_args, **_kwargs):
        raise requests.Timeout("private network details")

    monkeypatch.setattr(worker.requests, "post", timeout)
    job = job_after_generate(backend_client, registered_user["token"])
    assert job["status"] == "failed"
    assert job["error"] == "The AI service timed out before completing the job."


def test_invalid_signed_media_link_is_rejected(backend_client):
    response = backend_client.get("/media/result.png?token=broken")
    assert response.status_code == 401
    assert response.get_json()["error"]["code"] == "invalid_media_link"


def test_health_reports_ai_outage_without_failing_backend(backend_client, monkeypatch):
    def unavailable(*_args, **_kwargs):
        raise requests.ConnectionError("offline")

    monkeypatch.setattr(luma_backend.requests, "get", unavailable)
    response = backend_client.get("/api/v1/health")
    assert response.status_code == 200
    data = response.get_json()
    assert data["status"] == "ok"
    assert data["dependencies"] == {"database": "ok", "ai_service": "unavailable"}
