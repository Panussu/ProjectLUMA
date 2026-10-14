"""Regression checks for malformed credentials, AI inputs, and upload retries."""
import io

import pytest

from luma_backend import worker


@pytest.mark.parametrize("route", ["register", "login"])
@pytest.mark.parametrize("payload", [["bad"], "bad", {"username": 123, "password": "password123"}, {"username": "student", "password": ["password123"]}])
def test_malformed_credentials_return_validation_error(backend_client, route, payload):
    # Invalid input must produce a controlled response rather than crash.
    response = backend_client.post(f"/api/v1/auth/{route}", json=payload)
    assert response.status_code == 400
    assert response.get_json()["error"]["code"] == "validation_error"


@pytest.mark.parametrize("options", [{"width": 256.9}, {"steps": 20.5}, {"seed": True}, {"clip_skip": 1.5}, {"prompt": ["a", "b", "c"]}])
def test_ai_rejects_invalid_input_types(ai_client, options):
    # Direct AI callers receive the same strict validation as Backend callers.
    response = ai_client.post("/v1/generate", json={"prompt": "test image", **options}, headers={"X-LUMA-Service-Token": "test-service-token"})
    assert response.status_code == 400


def test_upload_retry_resends_complete_image(backend_app, monkeypatch):
    # Simulate requests consuming the stream before the queue rejects a request.
    stream = io.BytesIO(b"complete image bytes")
    sent = []
    def post(url, **kwargs):
        sent.append(kwargs["files"]["image"][1].read())
        return type("Response", (), {"status_code": 429 if len(sent) == 1 else 200})()
    monkeypatch.setattr(worker.requests, "post", post)
    backend_app.config.update(AI_QUEUE_MAX_RETRIES=1, AI_QUEUE_RETRY_DELAY=0)
    response = worker.post_with_queue_retry("http://ai.test/v1/edit", backend_app, files={"image": ("image.png", stream, "image/png")})
    assert response.status_code == 200
    assert sent == [b"complete image bytes", b"complete image bytes"]
