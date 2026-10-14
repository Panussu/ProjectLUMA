"""Regression tests for browser integration and private media access."""
import io
from pathlib import Path

import pytest
from itsdangerous import URLSafeTimedSerializer

from luma_backend.extensions import db
from luma_backend.models import Job


@pytest.mark.parametrize("method", ["PUT", "DELETE"])
def test_favorites_cors_allows_browser_mutations(backend_client, method):
    response = backend_client.options("/api/v1/prompts/favorites/1", headers={
        "Origin": "http://frontend.test", "Access-Control-Request-Method": method,
        "Access-Control-Request-Headers": "authorization,content-type",
    })
    assert method in response.headers.get("Access-Control-Allow-Methods", "")


@pytest.mark.parametrize("key", ["development-secret-change-me", "replace-with-a-long-random-value"])
def test_public_example_secret_cannot_sign_private_media(backend_app, backend_client, registered_user, png_bytes, key):
    with backend_app.app_context():
        job = Job(user_id=registered_user["user"]["id"], type="generate", prompt="private image", status="completed", result_filename="private.png")
        db.session.add(job)
        db.session.commit()
        payload = {"job": job.id, "user": job.user_id, "file": job.result_filename}
        (Path(backend_app.config["MEDIA_ROOT"]) / "private.png").write_bytes(png_bytes)
    token = URLSafeTimedSerializer(key, salt="luma-media").dumps(payload)
    assert backend_client.get("/media/private.png", query_string={"token": token}).status_code == 401


@pytest.mark.parametrize("payload", [["bad"], "bad", 123])
def test_favorite_requires_object_body(backend_client, registered_user, payload):
    headers = {"Authorization": "Bearer " + registered_user["token"]}
    assert backend_client.post("/api/v1/prompts/favorites", json=payload, headers=headers).status_code == 400
    favorite = backend_client.post("/api/v1/prompts/favorites", json={"title": "test", "prompt": "test prompt"}, headers=headers).get_json()["favorite"]
    assert backend_client.put(f"/api/v1/prompts/favorites/{favorite['id']}", json=payload, headers=headers).status_code == 400


@pytest.mark.parametrize("option", [{"width": 1088}, {"height": 1536}, {"steps": 51}])
def test_backend_rejects_settings_outside_ai_limits(backend_client, registered_user, option):
    response = backend_client.post("/api/v1/jobs/generate", json={"prompt": "test image", **option}, headers={"Authorization": "Bearer " + registered_user["token"]})
    assert response.status_code == 400


def test_media_signature_payload_must_be_object(backend_app, backend_client):
    token = URLSafeTimedSerializer(backend_app.config["SECRET_KEY"], salt="luma-media").dumps(["bad"])
    assert backend_client.get("/media/test.png", query_string={"token": token}).status_code == 401


def test_signed_media_tokens_are_not_logged(backend_client, caplog):
    backend_client.get("/media/test.png?token=private-signature-fixture")
    assert "private-signature-fixture" not in caplog.text


@pytest.mark.parametrize("options", [{"cfg_scale": "nan"}, {"cfg_scale": "99"}, {"clip_skip": "13"}])
def test_ai_edit_validates_settings(ai_client, png_bytes, options):
    response = ai_client.post("/v1/edit", data={"prompt": "test image", **options}, files={"image": ("image.png", png_bytes, "image/png")}, headers={"X-LUMA-Service-Token": "test-service-token"})
    assert response.status_code == 400


def test_forge_request_attaches_configured_basic_auth(ai_module, monkeypatch):
    seen = []
    def request(method, url, **kwargs):
        seen.append(kwargs["auth"])
        return type("Response", (), {"ok": True})()
    monkeypatch.setattr(ai_module.requests, "request", request)
    config = {"FORGE_URL": "http://forge.test", "FORGE_USERNAME": "fixture-user", "FORGE_PASSWORD": "fixture-password", "FORGE_CONNECT_TIMEOUT": 1, "FORGE_READ_TIMEOUT": 1}
    ai_module.forge_request(config, "GET", "/sdapi/v1/options")
    config["FORGE_USERNAME"] = ""
    ai_module.forge_request(config, "GET", "/sdapi/v1/options")
    assert seen == [("fixture-user", "fixture-password"), None]


def test_malformed_optional_ai_metadata_does_not_fail_valid_image(backend_app, backend_client, registered_user, png_bytes, monkeypatch):
    from luma_backend import worker
    from test_cancellation_and_queue import MockResponse
    monkeypatch.setattr(worker.requests, "post", lambda *args, **kwargs: MockResponse(content=png_bytes, headers={"Content-Type": "image/png", "X-LUMA-Seed": "not-an-integer", "X-LUMA-Steps": "nan", "X-LUMA-CFG-Scale": "inf"}))
    headers = {"Authorization": "Bearer " + registered_user["token"]}
    created = backend_client.post("/api/v1/jobs/generate", json={"prompt": "test image", "seed": 42}, headers=headers).get_json()["job"]
    job = backend_client.get(f"/api/v1/jobs/{created['id']}", headers=headers).get_json()["job"]
    assert job["status"] == "completed"
    assert job["seed"] == 42
    assert "cfg_scale" not in job["ai_result"]


@pytest.mark.parametrize("length", [33, 50, 75])
def test_truncated_edit_images_return_validation_error(backend_client, registered_user, png_bytes, length):
    response = backend_client.post("/api/v1/jobs/edit", data={"prompt": "edit image", "image": (io.BytesIO(png_bytes[:length]), "broken.png")}, headers={"Authorization": "Bearer " + registered_user["token"]})
    assert response.status_code == 400


def test_proxy_hides_provider_server_error(backend_client, monkeypatch):
    from luma_backend import ai_proxy
    def request(**kwargs):
        return type("Response", (), {"status_code": 500, "headers": {}, "json": lambda self: {"error": "private upstream configuration"}})()
    monkeypatch.setattr(ai_proxy.requests, "request", request)
    response = backend_client.get("/api/v1/models")
    assert response.status_code == 502
    assert "private upstream" not in response.get_data(as_text=True)
