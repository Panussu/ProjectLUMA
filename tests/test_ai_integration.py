"""Backend-to-AiEngine request contract and persisted job options."""

import io
import json

import pytest

from luma_backend import ai_catalog
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


class AiJsonResponse:
    ok = True
    status_code = 200

    def __init__(self, data):
        self.data = data

    def json(self):
        return self.data


class AiPreviewResponse:
    ok = True
    status_code = 200

    def __init__(self, image):
        self.content = image
        self.headers = {"Content-Type": "image/png"}


def test_catalog_and_signed_preview_stay_behind_backend(backend_client, registered_user, png_bytes, monkeypatch):
    calls = []

    def fake_get(url, **kwargs):
        calls.append((url, kwargs))
        if url.endswith("/v1/models"):
            return AiJsonResponse({"models": [{"name": "model xl", "has_preview": True, "preview_url": "/v1/preview/model/model xl"}], "count": 1})
        if url.endswith("/v1/preview/model/model%20xl"):
            return AiPreviewResponse(png_bytes)
        raise AssertionError(url)

    monkeypatch.setattr(ai_catalog.requests, "get", fake_get)
    assert backend_client.get("/api/v1/ai/models").status_code == 401
    response = backend_client.get("/api/v1/ai/models", headers=auth(registered_user["token"]))
    assert response.status_code == 200
    preview_url = response.get_json()["models"][0]["preview_url"]
    assert preview_url.startswith("/api/v1/ai/preview/model/model%20xl?token=")
    assert backend_client.get("/api/v1/ai/preview/model/model%20xl").status_code == 401
    assert backend_client.get(preview_url.replace("/model/", "/lora/")).status_code == 401
    preview = backend_client.get(preview_url)
    assert preview.status_code == 200
    assert preview.data == png_bytes
    assert calls[0][1]["headers"]["X-LUMA-Service-Token"] == "test-service-token"


def test_catalog_hides_ai_error_details(backend_client, registered_user, monkeypatch):
    class FailedResponse:
        ok = False
        status_code = 401
        text = "secret upstream configuration"

    monkeypatch.setattr(ai_catalog.requests, "get", lambda *args, **kwargs: FailedResponse())
    response = backend_client.get("/api/v1/ai/settings", headers=auth(registered_user["token"]))
    assert response.status_code == 502
    assert "secret upstream configuration" not in response.get_data(as_text=True)


@pytest.mark.parametrize(
    ("backend_path", "engine_path"),
    [
        ("models", "models"),
        ("loras", "loras"),
        ("samplers", "samplers"),
        ("schedulers", "schedulers"),
        ("settings", "settings"),
        ("styles", "styles"),
        ("styles/anime_illustrious", "styles/anime_illustrious"),
        ("queue/status", "queue/status"),
    ],
)
def test_catalog_routes_match_engine(backend_client, registered_user, monkeypatch, backend_path, engine_path):
    calls = []

    def fake_get(url, **kwargs):
        calls.append(url)
        return AiJsonResponse({"models": [], "loras": [], "count": 0})

    monkeypatch.setattr(ai_catalog.requests, "get", fake_get)
    response = backend_client.get(f"/api/v1/ai/{backend_path}", headers=auth(registered_user["token"]))
    assert response.status_code == 200
    assert calls == [f"http://ai.test/v1/{engine_path}"]

    # ตรวจสอบว่าเรียกผ่าน /api/v1/<path> ตรง ๆ โดยไม่มี /ai/ ก็ใช้งานได้เช่นกัน
    calls.clear()
    direct_response = backend_client.get(f"/api/v1/{backend_path}", headers=auth(registered_user["token"]))
    assert direct_response.status_code == 200
    assert calls == [f"http://ai.test/v1/{engine_path}"]

