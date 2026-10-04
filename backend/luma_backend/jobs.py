# รับงาน ตรวจข้อมูลและเจ้าของ แล้วสร้างลิงก์เข้าถึงภาพ
from __future__ import annotations

import math
import json
import re
import secrets
import uuid
from datetime import datetime, timezone
import requests
from pathlib import Path

from flask import Blueprint, current_app, jsonify, request, send_from_directory
from flask_jwt_extended import get_jwt_identity, jwt_required, verify_jwt_in_request
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer
from PIL import Image, UnidentifiedImageError

from .extensions import db
from .models import Job, JobAIOptions
from .worker import queue_job

jobs_blueprint = Blueprint("jobs", __name__)
media_blueprint = Blueprint("media", __name__)
ALLOWED_FORMATS = {"PNG", "JPEG", "WEBP"}
INTEGER_PATTERN = re.compile(r"^[+-]?\d+$")


# จัดรูปข้อผิดพลาดให้มี code และ message พร้อมรหัสสถานะ HTTP
def error_response(code: str, message: str, status: int):
    return jsonify({"error": {"code": code, "message": message}}), status


# แปลงและตรวจค่าตัวเลขกับช่วงที่อนุญาตก่อนนำไปใช้งาน
def parse_integer(value, name: str, minimum: int, maximum: int) -> int:
    if isinstance(value, bool):
        raise ValueError(f"{name} must be an integer.")
    if isinstance(value, int):
        parsed = value
    elif isinstance(value, str) and INTEGER_PATTERN.fullmatch(value.strip()):
        parsed = int(value)
    else:
        raise ValueError(f"{name} must be an integer.")
    if not minimum <= parsed <= maximum:
        raise ValueError(f"{name} must be between {minimum} and {maximum}.")
    return parsed


# เตรียมข้อความคำสั่งและตรวจความยาวก่อนส่งเข้ากระบวนการภาพ
def parse_prompt(value) -> str:
    if not isinstance(value, str):
        raise ValueError("Prompt must be a string.")
    prompt = value.strip()
    if not 3 <= len(prompt) <= 1000:
        raise ValueError("Prompt must contain between 3 and 1000 characters.")
    return prompt


def parse_ai_options(data: dict) -> dict:
    """Validate optional generation controls before persisting or forwarding them."""
    options = {}
    for field in ("model", "sampler", "scheduler", "style_preset"):
        value = data.get(field)
        if value is None or value == "":
            continue
        if not isinstance(value, str):
            raise ValueError(f"{field} must be a string.")
        value = value.strip()
        if not value or len(value) > 255 or any(ord(char) < 32 for char in value):
            raise ValueError(f"{field} must be a non-empty string of at most 255 characters.")
        options[field] = value

    if data.get("cfg_scale") not in (None, ""):
        try:
            value = float(data["cfg_scale"])
        except (TypeError, ValueError) as exc:
            raise ValueError("cfg_scale must be a number.") from exc
        if not math.isfinite(value) or not 1 <= value <= 30:
            raise ValueError("cfg_scale must be between 1 and 30.")
        options["cfg_scale"] = value
    if data.get("clip_skip") not in (None, ""):
        options["clip_skip"] = parse_integer(data["clip_skip"], "clip_skip", 1, 12)

    loras = data.get("loras")
    if loras is not None:
        if not isinstance(loras, list) or len(loras) > 8:
            raise ValueError("loras must be a list of at most 8 items.")
        parsed_loras = []
        for item in loras:
            if isinstance(item, str):
                name = item.strip()
                parsed = name
            elif isinstance(item, dict) and set(item) <= {"name", "weight"}:
                name = item.get("name")
                if not isinstance(name, str):
                    raise ValueError("Each LoRA must have a valid name.")
                name = name.strip()
                try:
                    weight = float(item.get("weight", 1.0))
                except (TypeError, ValueError) as exc:
                    raise ValueError("LoRA weight must be a number.") from exc
                if not math.isfinite(weight) or not 0 <= weight <= 2:
                    raise ValueError("LoRA weight must be between 0 and 2.")
                parsed = {"name": name, "weight": weight}
            else:
                raise ValueError("Each LoRA must be a name or an object with name and weight.")
            if not name or len(name) > 255 or any(char in name for char in "<>:\\/") or any(ord(char) < 32 for char in name):
                raise ValueError("Each LoRA must have a valid name.")
            parsed_loras.append(parsed)
        options["loras"] = parsed_loras
    return options


# อ่าน ID เจ้าของคำขอจาก JWT ที่ผ่านการตรวจแล้ว
def current_user_id() -> int:
    return int(get_jwt_identity())


# สร้างตัวลงลายเซ็นแบบมีเวลาโดยใช้กุญแจของ Backend และ salt สำหรับภาพ
def serializer() -> URLSafeTimedSerializer:
    return URLSafeTimedSerializer(current_app.config["SECRET_KEY"], salt="luma-media")


# สร้างลิงก์ภาพที่ผูกลายเซ็นกับงาน เจ้าของ และชื่อไฟล์ เฉพาะงานที่เสร็จแล้ว
def result_url(job: Job) -> str | None:
    if job.status != "completed" or not job.result_filename:
        return None
    token = serializer().dumps({"job": job.id, "user": job.user_id, "file": job.result_filename})
    return f"/media/{job.result_filename}?token={token}"


# รวมข้อมูลสถานะงานกับลิงก์ผลลัพธ์เพื่อส่งให้ Frontend
def serialized(job: Job) -> dict:
    return job.to_dict(result_url(job))


# ตรวจข้อมูลสร้างภาพแล้วส่งต่อการประมวลผลตามหน้าที่ของบริการนี้
@jobs_blueprint.post("/generate")
@jwt_required()
def generate():
    data = request.get_json(silent=True) or {}
    if not isinstance(data, dict):
        return error_response("validation_error", "The request body must be a JSON object.", 400)
    try:
        prompt = parse_prompt(data.get("prompt"))
        raw_negative_prompt = data.get("negative_prompt", "")
        if not isinstance(raw_negative_prompt, str):
            raise ValueError("Negative prompt must be a string.")
        negative_prompt = raw_negative_prompt.strip()
        if len(negative_prompt) > 1000:
            raise ValueError("Negative prompt cannot exceed 1000 characters.")
        width = parse_integer(data.get("width", 512), "width", 256, 1024)
        height = parse_integer(data.get("height", 512), "height", 256, 1024)
        if width % 64 or height % 64:
            raise ValueError("Width and height must be divisible by 64.")
        steps = parse_integer(data.get("steps", 20), "steps", 1, 50)
        seed = parse_integer(data.get("seed", secrets.randbits(32)), "seed", 0, 4_294_967_295)
        ai_options = parse_ai_options(data)
    except ValueError as exc:
        return error_response("validation_error", str(exc), 400)

    # สร้างระเบียนงานที่ผูกกับผู้ใช้และค่าที่ตรวจสอบแล้ว

    job = Job(
        user_id=current_user_id(),
        type="generate",
        prompt=prompt,
        negative_prompt=negative_prompt,
        width=width,
        height=height,
        steps=steps,
        seed=seed,
        ai_options=JobAIOptions(request_options=ai_options),
    )
    db.session.add(job)
    db.session.commit()
    # เก็บคำตอบสถานะเริ่มต้นก่อนส่งเข้า worker ที่อาจทำงานเสร็จเร็ว
    response = serialized(job)
    # ส่งออบเจ็กต์แอปจริงให้ worker ซึ่งสร้าง app context ของตนเอง
    queue_job(current_app._get_current_object(), job.id)
    return jsonify({"job": response}), 202


# ตรวจภาพที่อัปโหลดและพารามิเตอร์แก้ไขก่อนส่งต่อการประมวลผล
@jobs_blueprint.post("/edit")
@jwt_required()
def edit():
    # อ่านไฟล์จาก multipart form ของคำขอแก้ไขภาพ
    upload = request.files.get("image")
    if upload is None or not upload.filename:
        return error_response("validation_error", "An image file is required.", 400)
    try:
        prompt = parse_prompt(request.form.get("prompt"))
        strength = float(request.form.get("strength", "0.65"))
        if not math.isfinite(strength) or not 0 <= strength <= 1:
            raise ValueError("Strength must be between 0 and 1.")
        seed = parse_integer(request.form.get("seed", secrets.randbits(32)), "seed", 0, 4_294_967_295)
        raw_loras = request.form.get("loras")
        try:
            loras = json.loads(raw_loras) if raw_loras else None
        except ValueError as exc:
            raise ValueError("loras must be a JSON list.") from exc
        ai_options = parse_ai_options({**request.form.to_dict(), "loras": loras})
        with Image.open(upload.stream) as image:
            image.verify()
            image_format = image.format
            if image_format not in ALLOWED_FORMATS:
                raise ValueError("Only PNG, JPEG, and WebP images are accepted.")
        # ย้อนตำแหน่งไฟล์หลังตรวจภาพเพื่อให้อ่านหรือบันทึกจากจุดเริ่มต้น
        upload.stream.seek(0)
        with Image.open(upload.stream) as image:
            if image.width * image.height > 4_194_304:
                raise ValueError("The input image has too many pixels.")
        upload.stream.seek(0)
    except (Image.DecompressionBombError, OSError, ValueError, UnidentifiedImageError) as exc:
        return error_response("validation_error", str(exc) or "The uploaded file is not a valid image.", 400)

    # สร้างชื่อไฟล์ใหม่ ไม่ใช้ชื่อที่ผู้ใช้อัปโหลดเป็นชื่อจัดเก็บ

    source_filename = f"{uuid.uuid4()}.{image_format.lower().replace('jpeg', 'jpg')}"
    source_path = Path(current_app.config["UPLOAD_ROOT"]) / source_filename
    try:
        upload.save(source_path)
        job = Job(
            user_id=current_user_id(),
            type="edit",
            prompt=prompt,
            strength=strength,
            seed=seed,
            source_filename=source_filename,
            ai_options=JobAIOptions(request_options=ai_options),
        )
        db.session.add(job)
        db.session.commit()
    except Exception:
        db.session.rollback()
        source_path.unlink(missing_ok=True)
        raise
    response = serialized(job)
    queue_job(current_app._get_current_object(), job.id)
    return jsonify({"job": response}), 202


# อ่านงานล่าสุดเฉพาะเจ้าของ JWT พร้อมจำกัดจำนวนรายการ
@jobs_blueprint.get("")
@jwt_required()
def list_jobs():
    try:
        limit = parse_integer(request.args.get("limit", 20), "limit", 1, 100)
    except ValueError as exc:
        return error_response("validation_error", str(exc), 400)
    statement = db.select(Job).where(Job.user_id == current_user_id()).order_by(Job.created_at.desc()).limit(limit)
    jobs = db.session.scalars(statement).all()
    return jsonify({"jobs": [serialized(job) for job in jobs], "count": len(jobs)})


# ค้นหางานด้วยทั้งรหัสงานและเจ้าของ ป้องกันการเดา ID เพื่ออ่านงานผู้อื่น
@jobs_blueprint.get("/<job_id>")
@jwt_required()
def get_job(job_id: str):
    job = db.session.scalar(db.select(Job).where(Job.id == job_id, Job.user_id == current_user_id()))
    if job is None:
        return error_response("job_not_found", "The requested job does not exist.", 404)
    return jsonify({"job": serialized(job)})


# ขอยกเลิกงานและส่งสัญญาณหยุด GPU หากงานกำลังประมวลผลอยู่
@jobs_blueprint.post("/<job_id>/cancel")
@jwt_required()
def cancel_job(job_id: str):
    job = db.session.scalar(db.select(Job).where(Job.id == job_id, Job.user_id == current_user_id()))
    if job is None:
        return error_response("job_not_found", "The requested job does not exist.", 404)

    if job.status in ("completed", "failed", "cancelled"):
        return error_response("invalid_job_state", f"Cannot cancel a job that is already {job.status}.", 409)

    previous_status = job.status
    job.status = "cancelled"
    job.error = "Job was cancelled by the user."
    job.completed_at = datetime.now(timezone.utc)
    db.session.commit()

    # หากงานกำลังทำงานบน GPU ให้ส่งคำขอ interrupt ไปยัง AI Engine เพื่อคืน VRAM ทันที
    if previous_status == "processing":
        ai_url = f"{current_app.config['AI_SERVICE_URL'].rstrip('/')}/v1/interrupt"
        headers = {"X-LUMA-Service-Token": current_app.config["AI_SERVICE_TOKEN"]}
        try:
            requests.post(ai_url, headers=headers, timeout=(2, 5), allow_redirects=False)
        except requests.RequestException:
            current_app.logger.warning("Failed to forward interrupt signal to AI service for job %s", job_id)

    return jsonify({"job": serialized(job), "message": "Job cancelled successfully."}), 200


# ตรวจสิทธิ์เข้าถึงภาพก่อนอ่านไฟล์จากพื้นที่จัดเก็บของ Backend
@media_blueprint.get("/<path:filename>")
def media(filename: str):
    # รับ JWT ถ้ามี มิฉะนั้นตรวจลิงก์ภาพแบบมีลายเซ็นต่อไป
    verify_jwt_in_request(optional=True)
    identity = get_jwt_identity()
    if identity is not None:
        job = db.session.scalar(
            db.select(Job).where(
                Job.user_id == int(identity),
                Job.result_filename == filename,
                Job.status == "completed",
            )
        )
        if job is None:
            return error_response("media_not_found", "The requested image does not exist.", 404)
        return send_media_file(filename)

    # อ่านลิงก์ที่มีลายเซ็น ตรวจอายุ แล้วตรวจความสัมพันธ์กับระเบียนงาน

    token = request.args.get("token", "")
    if not token:
        return error_response(
            "authentication_required",
            "A bearer token or signed media link is required.",
            401,
        )
    try:
        payload = serializer().loads(token, max_age=current_app.config["MEDIA_TOKEN_MAX_AGE"])
    except SignatureExpired:
        return error_response("media_link_expired", "This image link has expired. Refresh the job to receive a new link.", 401)
    except BadSignature:
        return error_response("invalid_media_link", "This image link is invalid.", 401)
    if payload.get("file") != filename:
        return error_response("invalid_media_link", "This image link is invalid.", 401)
    job = db.session.get(Job, payload.get("job"))
    if (
        job is None
        or job.status != "completed"
        or job.user_id != payload.get("user")
        or job.result_filename != filename
    ):
        return error_response("media_not_found", "The requested image does not exist.", 404)
    return send_media_file(filename)


# ส่งภาพจากโฟลเดอร์ที่กำหนดและระบุให้แคชเป็นข้อมูลส่วนตัว
def send_media_file(filename: str):
    response = send_from_directory(current_app.config["MEDIA_ROOT"], filename, conditional=True)
    response.headers["Cache-Control"] = "private, max-age=3600"
    return response

