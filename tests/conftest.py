from __future__ import annotations

import importlib.util
import io
import sys
from pathlib import Path

import pytest
from PIL import Image

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
BACKEND_ROOT = REPOSITORY_ROOT / "backend"
AI_APP_PATH = REPOSITORY_ROOT / "ai-engine" / "app.py"

if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from luma_backend import create_app as create_backend_app  # noqa: E402
from luma_backend.extensions import db  # noqa: E402


def load_ai_module():
    spec = importlib.util.spec_from_file_location("luma_ai_app", AI_APP_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


@pytest.fixture()
def ai_app():
    module = load_ai_module()
    return module.create_app({"TESTING": True, "SERVICE_TOKEN": "test-service-token"})


@pytest.fixture()
def ai_client(ai_app):
    return ai_app.test_client()


@pytest.fixture()
def backend_app(tmp_path):
    app = create_backend_app(
        {
            "TESTING": True,
            "SQLALCHEMY_DATABASE_URI": f"sqlite:///{(tmp_path / 'test.db').as_posix()}",
            "MEDIA_ROOT": str(tmp_path / "media"),
            "UPLOAD_ROOT": str(tmp_path / "uploads"),
            "SECRET_KEY": "test-secret-that-is-longer-than-32-bytes",
            "JWT_SECRET_KEY": "test-jwt-secret-that-is-longer-than-32-bytes",
            "AI_SERVICE_TOKEN": "test-service-token",
            "AI_SERVICE_URL": "http://ai.test",
            "EXECUTE_JOBS_INLINE": True,
        }
    )
    with app.app_context():
        db.create_all()
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
    Image.new("RGB", (320, 320), "#6546a5").save(buffer, format="PNG")
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
