from __future__ import annotations

import base64
import io
import json

from fastapi.testclient import TestClient
from PIL import Image


def service_headers():
    return {"X-LUMA-Service-Token": "test-service-token"}


class FakeForgeResponse:
    def __init__(self, payload, status_code=200):
        self._payload = payload
        self.status_code = status_code
        self.ok = 200 <= status_code < 300
        self.text = ""

    def json(self):
        return self._payload


def test_health_is_public(ai_client):
    response = ai_client.get("/health")
    assert response.status_code == 200
    assert response.json()["service"] == "luma-ai"


def test_fastapi_exposes_the_private_contract_in_openapi(ai_client):
    response = ai_client.get("/openapi.json")
    assert response.status_code == 200
    assert response.json()["info"]["title"] == "LUMA AI Service"
    assert {"/health", "/v1/generate", "/v1/edit"} <= set(response.json()["paths"])


def test_private_endpoint_rejects_missing_token(ai_client):
    response = ai_client.post("/v1/generate", json={"prompt": "a valid prompt"})
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "unauthorized"


def test_generate_returns_repeatable_png(ai_client):
    payload = {"prompt": "a glowing garden at night", "width": 256, "height": 320, "seed": 42}
    first = ai_client.post("/v1/generate", json=payload, headers=service_headers())
    second = ai_client.post("/v1/generate", json=payload, headers=service_headers())
    assert first.status_code == 200
    assert first.headers["content-type"] == "image/png"
    assert first.headers["X-LUMA-Seed"] == "42"
    assert first.content == second.content
    image = Image.open(io.BytesIO(first.content))
    assert image.size == (256, 320)


def test_generation_dimensions_are_validated(ai_client):
    response = ai_client.post(
        "/v1/generate",
        json={"prompt": "a valid prompt", "width": 300, "height": 512},
        headers=service_headers(),
    )
    assert response.status_code == 400
    assert "divisible by 64" in response.json()["error"]["message"]


def test_edit_returns_png(ai_client, png_bytes):
    response = ai_client.post(
        "/v1/edit",
        data={"prompt": "make this vintage", "strength": "0.7", "seed": "8"},
        files={"image": ("source.png", png_bytes, "image/png")},
        headers=service_headers(),
    )
    assert response.status_code == 200
    assert response.headers["content-type"] == "image/png"
    assert Image.open(io.BytesIO(response.content)).size == (320, 320)


def forge_app(ai_module):
    return ai_module.create_app(
        {
            "TESTING": True,
            "SERVICE_TOKEN": "test-service-token",
            "PROVIDER_NAME": "forge",
            "FORGE_URL": "http://forge.test:7860",
            "FORGE_USERNAME": "",
            "FORGE_PASSWORD": "",
            "FORGE_CHECKPOINT": "classroom-model.safetensors",
            "FORGE_SAMPLER": "Euler",
            "FORGE_SCHEDULER": "",
            "FORGE_CFG_SCALE": 6.5,
            "FORGE_EDIT_STEPS": 18,
            "FORGE_CONNECT_TIMEOUT": 1,
            "FORGE_READ_TIMEOUT": 10,
        }
    )


def forge_image_response(png_bytes, seed=777):
    return FakeForgeResponse(
        {
            "images": [base64.b64encode(png_bytes).decode("ascii")],
            "info": json.dumps({"seed": seed}),
        }
    )


def test_forge_generate_translates_payload_and_decodes_image(ai_module, png_bytes, monkeypatch):
    captured = {}

    def fake_request(method, url, **kwargs):
        captured.update({"method": method, "url": url, **kwargs})
        return forge_image_response(png_bytes)

    monkeypatch.setattr(ai_module.requests, "request", fake_request)
    with TestClient(forge_app(ai_module)) as client:
        response = client.post(
            "/v1/generate",
            json={
                "prompt": "a glass observatory under the stars",
                "negative_prompt": "blurry",
                "width": 512,
                "height": 768,
                "steps": 24,
                "seed": 42,
            },
            headers=service_headers(),
        )

    assert response.status_code == 200
    assert response.headers["content-type"] == "image/png"
    assert response.headers["X-LUMA-Seed"] == "777"
    assert response.headers["X-LUMA-Provider"] == "forge"
    assert captured["method"] == "POST"
    assert captured["url"] == "http://forge.test:7860/sdapi/v1/txt2img"
    assert captured["json"]["negative_prompt"] == "blurry"
    assert captured["json"]["steps"] == 24
    assert captured["json"]["override_settings"]["sd_model_checkpoint"] == "classroom-model.safetensors"


def test_forge_edit_sends_base64_source_image(ai_module, png_bytes, monkeypatch):
    captured = {}

    def fake_request(method, url, **kwargs):
        captured.update({"method": method, "url": url, **kwargs})
        return forge_image_response(png_bytes, seed=8)

    monkeypatch.setattr(ai_module.requests, "request", fake_request)
    with TestClient(forge_app(ai_module)) as client:
        response = client.post(
            "/v1/edit",
            data={"prompt": "make the colors warmer", "strength": "0.55", "seed": "8"},
            files={"image": ("source.png", png_bytes, "image/png")},
            headers=service_headers(),
        )

    assert response.status_code == 200
    assert captured["url"] == "http://forge.test:7860/sdapi/v1/img2img"
    assert captured["json"]["denoising_strength"] == 0.55
    assert base64.b64decode(captured["json"]["init_images"][0]).startswith(b"\x89PNG")


def test_forge_health_reports_unavailable_provider(ai_module, monkeypatch):
    def connection_failed(*_args, **_kwargs):
        raise ai_module.requests.ConnectionError("offline")

    monkeypatch.setattr(ai_module.requests, "request", connection_failed)
    with TestClient(forge_app(ai_module)) as client:
        response = client.get("/health")
    assert response.status_code == 503
    assert response.json()["status"] == "unavailable"
    assert response.json()["provider"] == "webui-forge"

