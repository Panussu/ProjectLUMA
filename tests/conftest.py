from __future__ import annotations

import io

import pytest
from PIL import Image

from luma_backend import create_app
from luma_backend.extensions import db


@pytest.fixture()
def backend_app(tmp_path):
    app = create_app(
        {
            "TESTING": True,
            "SQLALCHEMY_DATABASE_URI": f"sqlite:///{(tmp_path / 'test.db').as_posix()}",
            "MEDIA_ROOT": str(tmp_path / "media"),
            "UPLOAD_ROOT": str(tmp_path / "uploads"),
            "JWT_SECRET_KEY": "test-jwt-secret",
            "SECRET_KEY": "test-app-secret",
            "AI_SERVICE_TOKEN": "test-service-token",
            "AI_SERVICE_URL": "http://ai.test",
            "CORS_ORIGINS": ["http://frontend.test"],
            "EXECUTE_JOBS_INLINE": True,
        }
    )
    yield app
    with app.app_context():
        db.session.remove()
        db.drop_all()


@pytest.fixture()
def backend_client(backend_app):
    return backend_app.test_client()


@pytest.fixture()
def png_bytes():
    buffer = io.BytesIO()
    Image.new("RGB", (64, 64), "#6544cc").save(buffer, format="PNG")
    return buffer.getvalue()


@pytest.fixture()
def registered_user(backend_client):
    response = backend_client.post(
        "/api/v1/auth/register",
        json={"username": "student.one", "password": "correct-horse-battery"},
    )
    assert response.status_code == 201
    data = response.get_json()
    return {"token": data["access_token"], "user": data["user"]}
