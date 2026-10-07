# ทดสอบระบบ Image Interrogator (DeepDanbooru และ CLIP)
from __future__ import annotations

import io
from luma_backend import filters


class MockResponse:
    def __init__(self, status_code: int = 200, json_data: dict | None = None):
        self.status_code = status_code
        self._json_data = json_data or {}

    @property
    def ok(self):
        return 200 <= self.status_code < 300

    def json(self):
        return self._json_data


def test_interrogate_models_discovery(backend_client):
    res = backend_client.get("/api/v1/interrogate/models")
    assert res.status_code == 200
    data = res.get_json()
    model_ids = {m["id"] for m in data["models"]}
    assert "deepdanbooru" in model_ids
    assert "clip" in model_ids


def test_interrogate_validation(backend_client, png_bytes):
    # 1. Missing image
    res = backend_client.post("/api/v1/interrogate", data={"model": "deepdanbooru"})
    assert res.status_code == 400
    assert res.get_json()["error"]["code"] == "validation_error"

    # 2. Invalid model name
    res = backend_client.post(
        "/api/v1/interrogate",
        data={"file": (io.BytesIO(png_bytes), "test.png"), "model": "invalid_model"},
    )
    assert res.status_code == 400


def test_interrogate_forwarding_and_fallback(backend_client, png_bytes, monkeypatch):
    # 1. Forwarding to AiEngine when online
    upstream_calls = []

    def fake_post(url, **kwargs):
        upstream_calls.append((url, kwargs))
        return MockResponse(
            200,
            json_data={
                "status": "ok",
                "model": "deepdanbooru",
                "caption": "1girl, blue_hair, smile",
                "tags": ["1girl", "blue_hair", "smile"],
                "provider": "forge",
                "execution_ms": 110.0,
            },
        )

    monkeypatch.setattr(filters.requests, "post", fake_post)

    res = backend_client.post(
        "/api/v1/interrogate",
        data={"file": (io.BytesIO(png_bytes), "test.png"), "model": "deepdanbooru"},
    )
    assert res.status_code == 200
    data = res.get_json()
    assert data["model"] == "deepdanbooru"
    assert "1girl" in data["tags"]
    assert len(upstream_calls) == 1
    assert upstream_calls[0][1]["headers"]["X-LUMA-Service-Token"] == "test-service-token"

    # 2. Procedural Fallback when AiEngine offline
    def fake_fail(url, **kwargs):
        return MockResponse(503, json_data={"error": "unavailable"})

    monkeypatch.setattr(filters.requests, "post", fake_fail)

    res_fallback = backend_client.post(
        "/api/v1/interrogate",
        data={"file": (io.BytesIO(png_bytes), "test.png"), "model": "clip"},
    )
    assert res_fallback.status_code == 200
    fb_data = res_fallback.get_json()
    assert fb_data["model"] == "clip"
    assert "caption" in fb_data
    assert len(fb_data["tags"]) > 0
    assert fb_data["provider"] == "backend-procedural-interrogate"
