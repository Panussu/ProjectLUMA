"""Backend-to-AiEngine request contract and persisted job options."""

import io
import json

from luma_backend import worker


class AiImageResponse:
    ok = True
    status_code = 200

    def __init__(self, image):
        self.content = image
        self.headers = {
            "Content-Type": "image/png",
            "X-LUMA-Seed": "42",
            "X-LUMA-Provider": "development-procedural",
            "X-LUMA-Sampler": "Euler a",
            "X-LUMA-Steps": "28",
            "X-LUMA-Style-Preset": "anime_illustrious",
        }


def auth(token):
    return {"Authorization": f"Bearer {token}"}


def test_generate_forwards_and_persists_ai_controls(backend_client, registered_user, png_bytes, monkeypatch):
    calls = []

    def fake_post(url, **kwargs):
        calls.append((url, kwargs))
        return AiImageResponse(png_bytes)

    monkeypatch.setattr(worker.requests, "post", fake_post)
    options = {
        "model": "checkpoint-xl",
        "loras": [{"name": "detail", "weight": 0.7}],
        "sampler": "Euler a",
        "scheduler": "Karras",
        "cfg_scale": 7.5,
        "clip_skip": 2,
        "style_preset": "anime_illustrious",
    }
    response = backend_client.post(
        "/api/v1/jobs/generate",
        json={"prompt": "portrait at sunset", **options},
        headers=auth(registered_user["token"]),
    )
    assert response.status_code == 202
    url, sent = calls[0]
    assert url == "http://ai.test/v1/generate"
    assert sent["headers"]["X-LUMA-Service-Token"] == "test-service-token"
    for key, value in options.items():
        assert sent["json"][key] == value

    job_id = response.get_json()["job"]["id"]
    job = backend_client.get(f"/api/v1/jobs/{job_id}", headers=auth(registered_user["token"])).get_json()["job"]
    assert job["ai_options"] == options
    assert job["ai_result"]["style_preset"] == "anime_illustrious"
    assert job["steps"] == 28
    assert job["seed"] == 42


def test_edit_forwards_ai_controls_as_multipart(backend_client, registered_user, png_bytes, monkeypatch):
    calls = []

    def fake_post(url, **kwargs):
        calls.append((url, kwargs))
        return AiImageResponse(png_bytes)

    monkeypatch.setattr(worker.requests, "post", fake_post)
    response = backend_client.post(
        "/api/v1/jobs/edit",
        data={
            "prompt": "make the sky warm",
            "image": (io.BytesIO(png_bytes), "source.png"),
            "model": "checkpoint-xl",
            "loras": json.dumps(["detail"]),
            "cfg_scale": "6.5",
            "style_preset": "anime_illustrious",
        },
        headers=auth(registered_user["token"]),
        content_type="multipart/form-data",
    )
    assert response.status_code == 202
    url, sent = calls[0]
    assert url == "http://ai.test/v1/edit"
    assert sent["data"]["model"] == "checkpoint-xl"
    assert json.loads(sent["data"]["loras"]) == ["detail"]
    assert sent["data"]["cfg_scale"] == "6.5"
    assert sent["data"]["style_preset"] == "anime_illustrious"


def test_invalid_ai_controls_are_rejected_before_queueing(backend_client, registered_user):
    token = auth(registered_user["token"])
    invalid = (
        {"cfg_scale": "NaN"},
        {"loras": "not-a-list"},
        {"loras": [{"name": "detail", "weight": "inf"}]},
        {"clip_skip": 0},
    )
    for options in invalid:
        response = backend_client.post(
            "/api/v1/jobs/generate", json={"prompt": "red paper lantern", **options}, headers=token
        )
        assert response.status_code == 400
        assert response.get_json()["error"]["code"] == "validation_error"
