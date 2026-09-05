from __future__ import annotations

import io
from pathlib import Path
from urllib.parse import urlsplit

from luma_backend import worker


class FakeAiResponse:
    def __init__(self, image: bytes):
        self.status_code = 200
        self.ok = True
        self.content = image
        self.text = ""
        self.headers = {
            "Content-Type": "image/png",
            "X-LUMA-Seed": "1234",
            "X-LUMA-Provider": "test-provider",
        }

    def json(self):
        return {}


class InvalidAiResponse(FakeAiResponse):
    def __init__(self, content: bytes = b"not-an-image", content_type: str = "image/png"):
        super().__init__(content)
        self.headers["Content-Type"] = content_type


def authorization(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def test_registration_login_and_current_user(backend_client, registered_user):
    duplicate = backend_client.post(
        "/api/v1/auth/register",
        json={"username": "STUDENT.ONE", "password": "another-password"},
    )
    assert duplicate.status_code == 409

    login = backend_client.post(
        "/api/v1/auth/login",
        json={"username": "Student.One", "password": "correct-horse-battery"},
    )
    assert login.status_code == 200

    me = backend_client.get("/api/v1/auth/me", headers=authorization(registered_user["token"]))
    assert me.status_code == 200
    assert me.get_json()["user"]["username"] == "student.one"


def test_invalid_registration_is_rejected(backend_client):
    response = backend_client.post("/api/v1/auth/register", json={"username": "x", "password": "short"})
    assert response.status_code == 400
    assert response.get_json()["error"]["code"] == "validation_error"


def test_generate_job_completes_and_media_link_works(
    backend_client, registered_user, png_bytes, monkeypatch
):
    monkeypatch.setattr(worker.requests, "post", lambda *args, **kwargs: FakeAiResponse(png_bytes))
    token = registered_user["token"]
    created = backend_client.post(
        "/api/v1/jobs/generate",
        json={"prompt": "a paper city in soft daylight", "width": 512, "height": 512, "seed": 99, "steps": 15},
        headers=authorization(token),
    )
    assert created.status_code == 202
    job_id = created.get_json()["job"]["id"]

    result = backend_client.get(f"/api/v1/jobs/{job_id}", headers=authorization(token))
    assert result.status_code == 200
    job = result.get_json()["job"]
    assert job["status"] == "completed"
    assert job["provider"] == "test-provider"
    assert job["seed"] == 1234

    media = backend_client.get(job["result_url"])
    assert media.status_code == 200
    assert media.data == png_bytes


def test_media_accepts_owner_bearer_token_and_rejects_other_users(
    backend_client, registered_user, png_bytes, monkeypatch
):
    monkeypatch.setattr(worker.requests, "post", lambda *args, **kwargs: FakeAiResponse(png_bytes))
    created = backend_client.post(
        "/api/v1/jobs/generate",
        json={"prompt": "a private bearer media result"},
        headers=authorization(registered_user["token"]),
    )
    job_id = created.get_json()["job"]["id"]
    job = backend_client.get(
        f"/api/v1/jobs/{job_id}", headers=authorization(registered_user["token"])
    ).get_json()["job"]
    media_path = urlsplit(job["result_url"]).path

    owner_download = backend_client.get(
        media_path, headers=authorization(registered_user["token"])
    )
    assert owner_download.status_code == 200
    assert owner_download.data == png_bytes

    second = backend_client.post(
        "/api/v1/auth/register",
        json={"username": "media.viewer", "password": "another-valid-password"},
    ).get_json()
    denied = backend_client.get(
        media_path, headers=authorization(second["access_token"])
    )
    assert denied.status_code == 404


def test_media_requires_bearer_token_or_signed_link(backend_client):
    response = backend_client.get("/media/missing.png")
    assert response.status_code == 401
    assert response.get_json()["error"]["code"] == "authentication_required"


def test_edit_job_accepts_valid_image(
    backend_client, registered_user, png_bytes, monkeypatch
):
    monkeypatch.setattr(worker.requests, "post", lambda *args, **kwargs: FakeAiResponse(png_bytes))
    created = backend_client.post(
        "/api/v1/jobs/edit",
        data={
            "prompt": "make this scene warmer",
            "strength": "0.6",
            "image": (io.BytesIO(png_bytes), "source.png"),
        },
        headers=authorization(registered_user["token"]),
        content_type="multipart/form-data",
    )
    assert created.status_code == 202
    job_id = created.get_json()["job"]["id"]
    result = backend_client.get(f"/api/v1/jobs/{job_id}", headers=authorization(registered_user["token"]))
    assert result.get_json()["job"]["status"] == "completed"


def test_jobs_are_isolated_between_users(
    backend_client, registered_user, png_bytes, monkeypatch
):
    monkeypatch.setattr(worker.requests, "post", lambda *args, **kwargs: FakeAiResponse(png_bytes))
    created = backend_client.post(
        "/api/v1/jobs/generate",
        json={"prompt": "private image prompt"},
        headers=authorization(registered_user["token"]),
    )
    job_id = created.get_json()["job"]["id"]

    second = backend_client.post(
        "/api/v1/auth/register",
        json={"username": "student.two", "password": "another-valid-password"},
    ).get_json()
    response = backend_client.get(
        f"/api/v1/jobs/{job_id}", headers=authorization(second["access_token"])
    )
    assert response.status_code == 404


def test_protected_routes_require_authentication(backend_client):
    response = backend_client.get("/api/v1/jobs")
    assert response.status_code == 401
    assert response.get_json()["error"]["code"] == "authentication_required"


def test_corrupt_ai_response_fails_job_without_publishing_media(
    backend_app, backend_client, registered_user, monkeypatch
):
    monkeypatch.setattr(worker.requests, "post", lambda *args, **kwargs: InvalidAiResponse())
    created = backend_client.post(
        "/api/v1/jobs/generate",
        json={"prompt": "response validation example"},
        headers=authorization(registered_user["token"]),
    )
    job_id = created.get_json()["job"]["id"]

    job = backend_client.get(
        f"/api/v1/jobs/{job_id}", headers=authorization(registered_user["token"])
    ).get_json()["job"]
    assert job["status"] == "failed"
    assert job["result_url"] is None
    assert list(Path(backend_app.config["MEDIA_ROOT"]).iterdir()) == []
