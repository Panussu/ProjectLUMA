# fixture ร่วมของ pytest ใช้ข้อมูลชั่วคราวแทนฐานข้อมูลผู้ใช้จริง
from __future__ import annotations

import importlib.util
import io
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from PIL import Image

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
BACKEND_ROOT = REPOSITORY_ROOT / "backend"
AI_APP_PATH = REPOSITORY_ROOT / "ai-engine" / "app.py"

if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from luma_backend import create_app as create_backend_app  # noqa: E402
from luma_backend.extensions import db  # noqa: E402


# โหลดโมดูล AI จากเส้นทางไฟล์เพื่อแยกการสร้างแอปทดสอบ
def load_ai_module():
    spec = importlib.util.spec_from_file_location("luma_ai_app", AI_APP_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


# จัดเตรียมโมดูล AI ให้แต่ละกรณีทดสอบ
@pytest.fixture()
def ai_module():
    return load_ai_module()


# สร้างแอป AI สำหรับทดสอบด้วยโทเคนที่กำหนดไว้ใน fixture
@pytest.fixture()
def ai_app(ai_module):
    return ai_module.create_app({"TESTING": True, "SERVICE_TOKEN": "test-service-token"})


# เปิด test client ของ FastAPI และปิดเมื่อจบกรณีทดสอบ
@pytest.fixture()
def ai_client(ai_app):
    with TestClient(ai_app) as client:
        yield client


# ใช้ฐานข้อมูลและโฟลเดอร์ชั่วคราวสำหรับทดสอบ แล้วล้าง session และตารางเมื่อจบ
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
        # สร้างตารางที่ยังไม่มี ไม่ใช่เครื่องมือย้ายโครงสร้างฐานข้อมูลเดิม
        db.create_all()
    yield app
    with app.app_context():
        db.session.remove()
        db.drop_all()


# สร้าง test client ของ Flask เพื่อเรียก API โดยไม่เปิดพอร์ตจริง
@pytest.fixture()
def backend_client(backend_app):
    return backend_app.test_client()


# สร้างไฟล์ PNG ในหน่วยความจำสำหรับทดสอบอัปโหลดและผลลัพธ์
@pytest.fixture()
def png_bytes():
    # ใช้บัฟเฟอร์ในหน่วยความจำแทนไฟล์ชั่วคราวสำหรับข้อมูลภาพ
    buffer = io.BytesIO()
    Image.new("RGB", (320, 320), "#6546a5").save(buffer, format="PNG")
    return buffer.getvalue()


# สมัครบัญชีทดสอบและคืนทั้งข้อมูลผู้ใช้กับโทเคน
@pytest.fixture()
def registered_user(backend_client):
    response = backend_client.post(
        "/api/v1/auth/register",
        json={"username": "student.one", "password": "correct-horse-battery"},
    )
    assert response.status_code == 201
    data = response.get_json()
    return {"token": data["access_token"], "user": data["user"]}
