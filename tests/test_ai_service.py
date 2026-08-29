from __future__ import annotations

import io

from PIL import Image


def service_headers():
    return {"X-LUMA-Service-Token": "test-service-token"}


def test_health_is_public(ai_client):
    response = ai_client.get("/health")
    assert response.status_code == 200
    assert response.get_json()["service"] == "luma-ai"


def test_private_endpoint_rejects_missing_token(ai_client):
    response = ai_client.post("/v1/generate", json={"prompt": "a valid prompt"})
    assert response.status_code == 401
    assert response.get_json()["error"]["code"] == "unauthorized"


def test_generate_returns_repeatable_png(ai_client):
    payload = {"prompt": "a glowing garden at night", "width": 256, "height": 320, "seed": 42}
    first = ai_client.post("/v1/generate", json=payload, headers=service_headers())
    second = ai_client.post("/v1/generate", json=payload, headers=service_headers())
    assert first.status_code == 200
    assert first.content_type == "image/png"
    assert first.headers["X-LUMA-Seed"] == "42"
    assert first.data == second.data
    image = Image.open(io.BytesIO(first.data))
    assert image.size == (256, 320)


def test_generation_dimensions_are_validated(ai_client):
    response = ai_client.post(
        "/v1/generate",
        json={"prompt": "a valid prompt", "width": 300, "height": 512},
        headers=service_headers(),
    )
    assert response.status_code == 400
    assert "divisible by 64" in response.get_json()["error"]["message"]


def test_edit_returns_png(ai_client, png_bytes):
    response = ai_client.post(
        "/v1/edit",
        data={"prompt": "make this vintage", "strength": "0.7", "seed": "8", "image": (io.BytesIO(png_bytes), "source.png")},
        headers=service_headers(),
        content_type="multipart/form-data",
    )
    assert response.status_code == 200
    assert response.content_type == "image/png"
    assert Image.open(io.BytesIO(response.data)).size == (320, 320)

