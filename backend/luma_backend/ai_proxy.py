"""AI Service Proxy Blueprint สำหรับส่งต่อคำขอจาก Frontend ไปยัง AI Engine (FastAPI)."""

from __future__ import annotations

from datetime import datetime, timezone

import requests
from flask import Blueprint, Response, current_app, jsonify, request

from .extensions import db
from .models import Job

# สร้าง Blueprint สำหรับ AI Proxy
ai_proxy_blueprint = Blueprint("ai_proxy", __name__)


def forward_ai_request(
    method: str,
    path: str,
    stream: bool = False,
    params: dict | None = None,
    json_data: dict | None = None,
    data: dict | None = None,
    files: dict | None = None,
) -> tuple[Response, int] | Response:
    """ส่งต่อคำขอ HTTP ไปยัง AI Engine พร้อมแนบโทเคนความปลอดภัย X-LUMA-Service-Token."""
    ai_base = current_app.config["AI_SERVICE_URL"].rstrip("/")
    url = f"{ai_base}{path}"
    headers = {
        "X-LUMA-Service-Token": current_app.config["AI_SERVICE_TOKEN"],
    }
    timeout = (
        current_app.config.get("AI_CONNECT_TIMEOUT", 5.0),
        current_app.config.get("AI_READ_TIMEOUT", 180.0),
    )

    try:
        resp = requests.request(
            method=method,
            url=url,
            headers=headers,
            params=params,
            json=json_data,
            data=data,
            files=files,
            timeout=timeout,
            stream=stream,
        )
    except requests.RequestException as exc:
        current_app.logger.warning("AI Engine unreachable at %s: %s", url, exc)
        return jsonify({
            "error": {
                "code": "ai_service_unavailable",
                "message": "The AI service is currently unreachable.",
            }
        }), 503

    # กรณีส่งภาพกลับ (Binary image response) เช่น ภาพพรีวิว หรือผลลัพธ์ PNG
    content_type = resp.headers.get("Content-Type", "")
    if stream or "image/" in content_type:
        excluded_headers = {"content-encoding", "content-length", "transfer-encoding", "connection"}
        response_headers = [
            (name, value) for (name, value) in resp.headers.items()
            if name.lower() not in excluded_headers
        ]
        return Response(resp.content, status=resp.status_code, headers=response_headers)

    # กรณีส่ง JSON ข้อมูลสถานะกลับ
    try:
        payload = resp.json()
        return jsonify(payload), resp.status_code
    except ValueError:
        return Response(resp.text, status=resp.status_code, content_type=content_type or "text/plain")


# ==================== 1. Models & LoRAs Catalog ====================

@ai_proxy_blueprint.get("/models")
def get_models():
    """ดึงรายชื่อโมเดล Checkpoints ที่มีอยู่ในเครื่อง AI Engine."""
    return forward_ai_request("GET", "/v1/models")


@ai_proxy_blueprint.get("/loras")
def get_loras():
    """ดึงรายชื่อ LoRA พร้อม Trigger Words ที่ติดตั้งใน AI Engine."""
    return forward_ai_request("GET", "/v1/loras")


@ai_proxy_blueprint.get("/preview/model/<path:name>")
def preview_model(name: str):
    """ส่งต่อคำขอดึงภาพตัวอย่างพรีวิวของ Checkpoint Model."""
    return forward_ai_request("GET", f"/v1/preview/model/{name}", stream=True)


@ai_proxy_blueprint.get("/preview/lora/<path:name>")
def preview_lora(name: str):
    """ส่งต่อคำขอดึงภาพตัวอย่างพรีวิวของ LoRA."""
    return forward_ai_request("GET", f"/v1/preview/lora/{name}", stream=True)


# ==================== 2. Generation Settings & Presets ====================

@ai_proxy_blueprint.get("/samplers")
def get_samplers():
    """ดึงรายชื่อ Sampler ทั้งหมดที่รองรับ (Euler, DPM++ 2M Karras ฯลฯ)."""
    return forward_ai_request("GET", "/v1/samplers")


@ai_proxy_blueprint.get("/schedulers")
def get_schedulers():
    """ดึงรายชื่อ Noise Schedulers (Karras, Exponential, Automatic ฯลฯ)."""
    return forward_ai_request("GET", "/v1/schedulers")


@ai_proxy_blueprint.get("/styles")
def get_styles():
    """ดึง 10 ชุด Curated Style Presets สำหรับปรับแต่ง Prompt อัตโนมัติ."""
    return forward_ai_request("GET", "/v1/styles")


@ai_proxy_blueprint.get("/styles/<style_id>")
def get_style(style_id: str):
    """ดึงข้อมูล Style Preset เฉพาะเจาะจงตาม ID."""
    return forward_ai_request("GET", f"/v1/styles/{style_id}")


@ai_proxy_blueprint.get("/settings")
def get_settings():
    """ดึงค่าคอนฟิกเริ่มต้น, ช่วงค่าที่อนุญาต, อัตราส่วนภาพ และ Presets คุณภาพ."""
    return forward_ai_request("GET", "/v1/settings")


# ==================== 3. Image Processing & Filters (API Workshop) ====================

@ai_proxy_blueprint.get("/filters")
def get_filters():
    """ดึงรายชื่อฟิลเตอร์ประมวลผลภาพ (Grayscale, Edge Detection, Blur, Invert)."""
    return forward_ai_request("GET", "/v1/filters")


@ai_proxy_blueprint.post("/process")
def process_filter_image():
    """ประมวลผลฟิลเตอร์ภาพตามมาตรฐาน API_Workshop โดยส่งต่อไปยัง AI Engine."""
    upload = request.files.get("file")
    if not upload or not upload.filename:
        return jsonify({"error": {"code": "validation_error", "message": "An image file is required."}}), 400

    operation = request.form.get("operation", "grayscale")
    files = {"file": (upload.filename, upload.stream, upload.content_type or "image/png")}
    data = {"operation": operation}
    return forward_ai_request("POST", "/process", files=files, data=data, stream=True)


# ==================== 4. Upscalers & Queue Status ====================

@ai_proxy_blueprint.get("/upscalers")
def get_upscalers():
    """ดึงรายชื่อ AI Upscalers ที่ระบบรองรับ (R-ESRGAN 4x+, SwinIR 4x ฯลฯ)."""
    return forward_ai_request("GET", "/v1/upscalers")


@ai_proxy_blueprint.get("/queue/status")
def get_queue_status():
    """ดึงสถานะคิวการทำงานของ GPU และจำนวนงานที่กำลังประมวลผล."""
    return forward_ai_request("GET", "/v1/queue/status")


@ai_proxy_blueprint.get("/progress")
def get_progress():
    """ดึงความคืบหน้าแบบเรียลไทม์ (0-100%) และ ETA ของงานที่กำลังรันบน GPU."""
    include_preview = request.args.get("include_preview", "false")
    return forward_ai_request("GET", "/v1/progress", params={"include_preview": include_preview})


@ai_proxy_blueprint.post("/interrupt")
def interrupt_generation():
    """ส่งสัญญาณยกเลิกงานสร้างภาพที่กำลังทำงานบน GPU ทันที."""
    # 1. บันทึกสถานะงานในฐานข้อมูลเป็น interrupted ก่อนเสมอ เพื่อให้ประวัติการสร้างภาพแม่นยำ
    try:
        data = request.get_json(silent=True) or {}
        job_id = data.get("job_id") or request.args.get("job_id")
        now = datetime.now(timezone.utc)
        if job_id:
            job = db.session.get(Job, str(job_id))
            if job and job.status in ("queued", "processing"):
                job.status = "interrupted"
                job.error = "Generation interrupted by user."
                job.progress = 0
                job.completed_at = now
                db.session.commit()
        else:
            active_jobs = db.session.scalars(
                db.select(Job).where(Job.status.in_(["processing", "queued"])).order_by(Job.created_at.desc())
            ).all()
            for j in active_jobs:
                j.status = "interrupted"
                j.error = "Generation interrupted by user."
                j.progress = 0
                j.completed_at = now
            if active_jobs:
                db.session.commit()
    except Exception as exc:
        current_app.logger.warning("Could not mark job as interrupted in database: %s", exc)

    # 2. ส่งสัญญาณ interrupt ไปยัง AI Engine และ WebUI Forge
    try:
        resp = forward_ai_request("POST", "/v1/interrupt")
        # ถ้า AI engine ตอบกลับมา ให้ส่ง response นั้นกลับ
        if isinstance(resp, tuple) and resp[1] >= 400:
            return jsonify({"status": "interrupted", "message": "Job marked as interrupted."}), 200
        return resp
    except Exception:
        return jsonify({"status": "interrupted", "message": "Job marked as interrupted."}), 200


@ai_proxy_blueprint.post("/skip")
def skip_generation():
    """ส่งสัญญาณข้ามขั้นตอนการสร้างภาพปัจจุบันบน GPU."""
    return forward_ai_request("POST", "/v1/skip")


# ==================== 5. Upscale & Interrogate ====================

@ai_proxy_blueprint.post("/upscale")
def upscale_image():
    """ส่งต่อคำขอขยายความละเอียดภาพ (Super Resolution) ด้วย AI Upscaler."""
    upload = request.files.get("image")
    if not upload or not upload.filename:
        return jsonify({"error": {"code": "validation_error", "message": "An image file is required."}}), 400

    files = {"image": (upload.filename, upload.stream, upload.content_type or "image/png")}
    data = {}
    if "scale_factor" in request.form:
        data["scale_factor"] = request.form.get("scale_factor")
    if "upscaler" in request.form:
        data["upscaler"] = request.form.get("upscaler")
    return forward_ai_request("POST", "/v1/upscale", files=files, data=data, stream=True)


@ai_proxy_blueprint.post("/interrogate")
def interrogate_image():
    """ส่งต่อคำขอถอดคำบรรยายหรือแท็กภาพ (DeepDanbooru / CLIP Interrogate)."""
    upload = request.files.get("image")
    if not upload or not upload.filename:
        return jsonify({"error": {"code": "validation_error", "message": "An image file is required."}}), 400

    model = request.form.get("model", "deepdanbooru")
    files = {"image": (upload.filename, upload.stream, upload.content_type or "image/png")}
    data = {"model": model}
    return forward_ai_request("POST", "/v1/interrogate", files=files, data=data)


# ==================== 6. PNG Info & Danbooru Tag Autocomplete ====================

@ai_proxy_blueprint.post("/png-info")
def png_info():
    """ส่งต่อคำขออ่าน Generation Metadata จากภาพ (Prompt, Negative Prompt, Settings)."""
    upload = request.files.get("file") or request.files.get("image")
    if not upload or not upload.filename:
        return jsonify({"error": {"code": "validation_error", "message": "An image file is required."}}), 400

    files = {"file": (upload.filename, upload.stream, upload.content_type or "image/png")}
    return forward_ai_request("POST", "/v1/png-info", files=files)


@ai_proxy_blueprint.get("/tags")
def get_tags():
    """ส่งต่อคำค้นหาแท็ก Danbooru สำหรับ Auto-Complete ใน Prompt."""
    q = request.args.get("q", "")
    limit = request.args.get("limit", "20")
    return forward_ai_request("GET", "/v1/tags", params={"q": q, "limit": limit})


