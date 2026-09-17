# เชื่อม Flask ฐานข้อมูล JWT CORS เส้นทาง API และตัวจัดการข้อผิดพลาด
from __future__ import annotations

import logging
import os
import uuid
from pathlib import Path
from typing import Any

import requests
from flask import Flask, g, jsonify, request
from flask_cors import CORS
from flask_jwt_extended import JWTManager

from .auth import auth_blueprint
from .config import Config
from .extensions import db
from .jobs import jobs_blueprint, media_blueprint

jwt = JWTManager()


# สร้างแอปจากค่ากำหนด เชื่อมบริการ และลงทะเบียนเส้นทางกับตัวจัดการข้อผิดพลาด
def create_app(test_config: dict[str, Any] | None = None) -> Flask:
    app = Flask(__name__)
    # โหลดค่าเริ่มต้นก่อนให้ test_config ปรับเฉพาะการทดสอบ
    app.config.from_object(Config())
    if test_config:
        app.config.update(test_config)

    # เตรียมโฟลเดอร์เก็บผลลัพธ์และภาพต้นทาง

    Path(app.config["MEDIA_ROOT"]).mkdir(parents=True, exist_ok=True)
    Path(app.config["UPLOAD_ROOT"]).mkdir(parents=True, exist_ok=True)

    # ตั้งรูปแบบบันทึกเพื่อใช้วิเคราะห์การทำงานของบริการ

    logging.basicConfig(
        level=getattr(logging, os.getenv("LOG_LEVEL", "INFO").upper(), logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    # เชื่อมฐานข้อมูล JWT และ CORS เข้ากับแอปที่สร้าง
    db.init_app(app)
    jwt.init_app(app)
    CORS(
        app,
        resources={r"/api/*": {"origins": app.config["CORS_ORIGINS"]}},
        allow_headers=["Content-Type", "Authorization"],
        methods=["GET", "POST", "OPTIONS"],
    )

    # จัดกลุ่มเส้นทางบัญชี งาน และภาพตาม prefix ของ API

    app.register_blueprint(auth_blueprint, url_prefix="/api/v1/auth")
    app.register_blueprint(jobs_blueprint, url_prefix="/api/v1/jobs")
    app.register_blueprint(media_blueprint, url_prefix="/media")

    with app.app_context():
        # สร้างตารางที่ยังไม่มี ไม่ใช่เครื่องมือย้ายโครงสร้างฐานข้อมูลเดิม
        db.create_all()

    # รับหรือสร้างรหัสคำขอเพื่อเชื่อมโยงบันทึกของ Nginx กับ Backend
    @app.before_request
    def attach_request_id():
        g.request_id = request.headers.get("X-Request-ID", str(uuid.uuid4()))[:128]

    # แนบรหัสคำขอและส่วนหัวควบคุมการตีความเนื้อหาในคำตอบ
    @app.after_request
    def response_headers(response):
        response.headers["X-Request-ID"] = getattr(g, "request_id", "")
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "same-origin"
        return response

    # ตรวจบริการที่พึ่งพาและส่งสถานะให้ผู้เรียกใช้ตรวจความพร้อม
    @app.get("/api/v1/health")
    def health():
        # ตรวจฐานข้อมูลแยกจาก AI เพื่อรายงานสาเหตุที่ไม่พร้อม
        database_status = "ok"
        try:
            db.session.execute(db.text("SELECT 1"))
        except Exception:
            app.logger.exception("Database health check failed")
            database_status = "unavailable"

        # เรียก health ของ AI โดยจำกัดเวลารอ

        ai_status = "unavailable"
        try:
            response = requests.get(f"{app.config['AI_SERVICE_URL'].rstrip('/')}/health", timeout=2)
            if response.ok:
                ai_status = "ok"
        except requests.RequestException:
            pass

        # HTTP status ของ health นี้อิงฐานข้อมูล ส่วน AI อยู่ใน dependencies

        status = "ok" if database_status == "ok" else "unavailable"
        code = 200 if status == "ok" else 503
        return jsonify(
            {
                "status": status,
                "service": "luma-backend",
                "dependencies": {"database": database_status, "ai_service": ai_status},
            }
        ), code

    # ตอบ JSON เมื่อคำขอเกินขนาดอัปโหลดที่กำหนด
    @app.errorhandler(413)
    def request_too_large(_error):
        return jsonify({"error": {"code": "request_too_large", "message": "The request exceeds the configured size limit."}}), 413

    # ตอบ JSON เมื่อไม่พบเส้นทางที่ผู้ใช้เรียก
    @app.errorhandler(404)
    def not_found(_error):
        return jsonify({"error": {"code": "not_found", "message": "The requested endpoint does not exist."}}), 404

    # บันทึกข้อผิดพลาดภายในแล้วตอบข้อความทั่วไปให้ผู้ใช้
    @app.errorhandler(500)
    def internal_error(error):
        app.logger.error("Unhandled error: %s", error)
        return jsonify({"error": {"code": "internal_error", "message": "The server could not complete the request."}}), 500

    # ปฏิเสธคำขอที่ไม่มีโทเคนยืนยันตัวตน
    @jwt.unauthorized_loader
    def missing_token(message):
        return jsonify({"error": {"code": "authentication_required", "message": message}}), 401

    # ปฏิเสธโทเคนที่ตรวจสอบไม่ได้
    @jwt.invalid_token_loader
    def invalid_token(message):
        return jsonify({"error": {"code": "invalid_token", "message": message}}), 401

    # แจ้งว่าโทเคนหมดอายุและต้องเข้าสู่ระบบใหม่
    @jwt.expired_token_loader
    def expired_token(_header, _payload):
        return jsonify({"error": {"code": "token_expired", "message": "The access token has expired."}}), 401

    return app

