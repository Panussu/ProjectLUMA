# fixture ร่วมของ pytest ใช้ข้อมูลชั่วคราวแทนฐานข้อมูลผู้ใช้จริง
from __future__ import annotations

import io

import pytest
from PIL import Image

from luma_backend import create_app
from luma_backend.extensions import db


# ใช้ฐานข้อมูลและโฟลเดอร์ชั่วคราวสำหรับทดสอบ แล้วล้าง session และตารางเมื่อจบ
@pytest.fixture()
def backend_app(tmp_path):
    app = create_app(
        {
            "TESTING": True,
            "SQLALCHEMY_DATABASE_URI": f"sqlite:///{(tmp_path / 'test.db').as_posix()}",
            "MEDIA_ROOT": str(tmp_path / "media"),
            "UPLOAD_ROOT": str(tmp_path / "uploads"),
            "JWT_SECRET_KEY": "test-jwt-secret-0123456789abcdef",
            "SECRET_KEY": "test-app-secret-0123456789abcdef",
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


# สร้าง test client ของ Flask เพื่อเรียก API โดยไม่เปิดพอร์ตจริง
@pytest.fixture()
def backend_client(backend_app):
    return backend_app.test_client()


# สร้างไฟล์ PNG ในหน่วยความจำสำหรับทดสอบอัปโหลดและผลลัพธ์
@pytest.fixture()
def png_bytes():
    # ใช้บัฟเฟอร์ในหน่วยความจำแทนไฟล์ชั่วคราวสำหรับข้อมูลภาพ
    buffer = io.BytesIO()
    Image.new("RGB", (64, 64), "#6544cc").save(buffer, format="PNG")
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
