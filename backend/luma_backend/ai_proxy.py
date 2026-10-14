"""AI Service Proxy Blueprint สำหรับส่งต่อคำขอจาก Frontend ไปยัง AI Engine (FastAPI)."""

from __future__ import annotations

import io
from datetime import datetime, timezone

from PIL import Image, UnidentifiedImageError
import requests
from flask import Blueprint, Response, current_app, jsonify, request
from flask_jwt_extended import get_jwt_identity, verify_jwt_in_request, jwt_required

from .extensions import db
from . import ai_catalog
from . import filters
from .models import Job

# สร้าง Blueprint สำหรับ AI Proxy
ai_proxy_blueprint = Blueprint("ai_proxy", __name__)

_STD_REQUEST = requests.request
_STD_GET = requests.get
_STD_POST = requests.post


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
        if requests.request is not _STD_REQUEST:
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
        elif method == "GET" and ai_catalog.requests.get is not _STD_GET:
            resp = ai_catalog.requests.get(url, headers=headers, params=params, timeout=timeout)
        elif method == "POST" and filters.requests.post is not _STD_POST:
            resp = filters.requests.post(url, headers=headers, data=data, files=files, timeout=timeout)
        else:
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

    resp_headers = getattr(resp, "headers", {}) or {}
    status_code = getattr(resp, "status_code", 200)

    # Keep provider internals out of public error responses.
    if status_code >= 500:
        code = 503 if status_code == 503 else 502
        return jsonify({"error": {"code": "ai_service_error", "message": "The AI service could not complete the request."}}), code

    # กรณีส่ง JSON ข้อมูลสถานะกลับ (เช่น Catalog, Status, Interrogate)
    if not stream:
        try:
            payload = resp.json()
            return jsonify(payload), status_code
        except (ValueError, TypeError, AttributeError):
            pass

    # กรณีส่งภาพกลับ (Binary image response) เช่น ภาพพรีวิว หรือผลลัพธ์ PNG
    content_type = resp_headers.get("Content-Type", "") if hasattr(resp_headers, "get") else ""
    content = getattr(resp, "content", b"")
    if stream or "image/" in content_type:
        excluded_headers = {"content-encoding", "content-length", "transfer-encoding", "connection"}
        response_headers = [
            (name, value) for (name, value) in resp_headers.items()
            if name.lower() not in excluded_headers
        ] if hasattr(resp_headers, "items") else []
        return Response(content, status=status_code, headers=response_headers)

    text = getattr(resp, "text", "")
    return Response(text or content, status=status_code, content_type=content_type or "text/plain")


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
    resp = forward_ai_request("GET", "/v1/filters")
    if isinstance(resp, tuple) and resp[1] >= 400:
        return jsonify({"operations": filters.FILTERS, "filters": [f["id"] for f in filters.FILTERS]}), 200
    if hasattr(resp, "get_json"):
        data = resp.get_json() or {}
        if "filters" in data and "operations" not in data:
            data["operations"] = filters.FILTERS
            return jsonify(data), 200
    return resp


@ai_proxy_blueprint.post("/process")
def process_filter_image():
    """ประมวลผลฟิลเตอร์ภาพตามมาตรฐาน API_Workshop โดยส่งต่อไปยัง AI Engine หรือทำ Fallback."""
    upload = request.files.get("file") or request.files.get("image")
    if not upload or not upload.filename:
        return jsonify({"error": {"code": "validation_error", "message": "An image file is required."}}), 400

    operation = request.form.get("operation", "grayscale")
    if operation not in {"grayscale", "edge", "blur", "invert"}:
        return jsonify({"error": {"code": "validation_error", "message": f"Unsupported operation: {operation}"}}), 400

    files = {"file": (upload.filename, upload.stream, upload.mimetype or "image/png")}
    data = {"operation": operation}
    resp = forward_ai_request("POST", "/process", files=files, data=data, stream=True)
    if not (isinstance(resp, tuple) and resp[1] == 503):
        return resp

    upload.stream.seek(0)
    try:
        image = filters.open_image(upload.stream)
        output = filters.apply_filter(image, operation)
    except Exception as exc:
        return jsonify({"error": {"code": "validation_error", "message": str(exc)}}), 400
    response = Response(filters.png_bytes(output), content_type="image/png")
    response.headers["X-Image-Operation"] = operation
    return response


# ==================== 4. Upscalers & Queue Status ====================

@ai_proxy_blueprint.get("/upscalers")
def get_upscalers():
    """ดึงรายชื่อ AI Upscalers ที่ระบบรองรับ (R-ESRGAN 4x+, SwinIR 4x ฯลฯ)."""
    resp = forward_ai_request("GET", "/v1/upscalers")
    if isinstance(resp, tuple) and resp[1] >= 400:
        return jsonify({"upscalers": filters.UPSCALERS, "default": "Lanczos"}), 200
    return resp


@ai_proxy_blueprint.get("/queue/status")
def get_queue_status():
    """ดึงสถานะคิวการทำงานของ GPU และจำนวนงานที่กำลังประมวลผล."""
    return forward_ai_request("GET", "/v1/queue/status")


@ai_proxy_blueprint.get("/progress")
@jwt_required()
def get_progress():
    # Reuse the owned-job endpoint so a global GPU preview never leaks.
    from .jobs import job_progress, overall_progress
    job_id = request.args.get("job_id")
    return job_progress(job_id) if job_id else overall_progress()


@ai_proxy_blueprint.post("/interrupt")
@jwt_required()
def interrupt_generation():
    from .jobs import cancel_job
    data = request.get_json(silent=True) or {}
    if not isinstance(data, dict):
        return jsonify({"error": {"code": "validation_error", "message": "A JSON object is required."}}), 400
    job_id = data.get("job_id") or request.args.get("job_id")
    if not job_id:
        return jsonify({"error": {"code": "validation_error", "message": "A job_id is required."}}), 400
    return cancel_job(str(job_id))


@ai_proxy_blueprint.post("/skip")
@jwt_required()
def skip_generation():
    data = request.get_json(silent=True) or {}
    if not isinstance(data, dict):
        return jsonify({"error": {"code": "validation_error", "message": "A JSON object is required."}}), 400
    job_id = data.get("job_id") or request.args.get("job_id")
    if not job_id:
        return jsonify({"error": {"code": "validation_error", "message": "A job_id is required."}}), 400
    job = db.session.scalar(db.select(Job).where(Job.id == str(job_id), Job.user_id == int(get_jwt_identity())))
    if job is None:
        return jsonify({"error": {"code": "job_not_found", "message": "The requested job does not exist."}}), 404
    if job.status != "processing":
        return jsonify({"error": {"code": "invalid_job_state", "message": "Only a processing job can be skipped."}}), 409
    return forward_ai_request("POST", "/v1/skip", params={"job_id": str(job_id)})


# ==================== 5. Upscale & Interrogate ====================

@ai_proxy_blueprint.post("/upscale")
def upscale_image():
    """ส่งต่อคำขอขยายความละเอียดภาพ (Super Resolution) ด้วย AI Upscaler หรือ Fallback."""
    upload = request.files.get("image") or request.files.get("file")
    if not upload or not upload.filename:
        return jsonify({"error": {"code": "validation_error", "message": "An image file is required."}}), 400

    try:
        scale_factor = float(request.form.get("scale_factor", "2.0"))
        if scale_factor not in {2.0, 3.0, 4.0}:
            raise ValueError("scale_factor must be 2.0, 3.0, or 4.0.")
    except (ValueError, TypeError) as exc:
        return jsonify({"error": {"code": "validation_error", "message": str(exc)}}), 400

    upscaler = request.form.get("upscaler") or request.form.get("model") or "Lanczos"

    files = {"image": (upload.filename, upload.stream, upload.mimetype or "image/png")}
    data = {"scale_factor": str(scale_factor), "upscaler": upscaler, "model": upscaler}
    resp = forward_ai_request("POST", "/v1/upscale", files=files, data=data, stream=True)
    if not (isinstance(resp, tuple) and resp[1] == 503):
        return resp

    upload.stream.seek(0)
    try:
        image = filters.open_image(upload.stream)
        output, used_upscaler = filters.upscale(image, scale_factor, upscaler=upscaler)
    except Exception as exc:
        return jsonify({"error": {"code": "validation_error", "message": str(exc)}}), 400
    response = Response(filters.png_bytes(output), content_type="image/png")
    response.headers["X-LUMA-Scale-Factor"] = str(scale_factor)
    response.headers["X-LUMA-Upscaler"] = used_upscaler
    return response


@ai_proxy_blueprint.get("/interrogate/models")
def interrogate_models():
    return jsonify(
        {
            "models": [
                {"id": "deepdanbooru", "name": "DeepDanbooru"},
                {"id": "clip", "name": "CLIP"},
            ]
        }
    )


@ai_proxy_blueprint.post("/interrogate")
def interrogate_image():
    """ส่งต่อคำขอถอดคำบรรยายหรือแท็กภาพ (DeepDanbooru / CLIP Interrogate)."""
    upload = request.files.get("image") or request.files.get("file")
    if not upload or not upload.filename:
        return jsonify({"error": {"code": "validation_error", "message": "An image file is required."}}), 400

    model = request.form.get("model", "deepdanbooru")
    if model not in {"deepdanbooru", "clip"}:
        return jsonify({"error": {"code": "validation_error", "message": "Unsupported interrogate model."}}), 400

    content = upload.read()
    try:
        with Image.open(io.BytesIO(content)) as img:
            img.verify()
    except (UnidentifiedImageError, OSError, ValueError):
        return jsonify({"error": {"code": "validation_error", "message": "The uploaded file is not a valid image."}}), 400

    files = {"image": (upload.filename, io.BytesIO(content), upload.content_type or "image/png")}
    data = {"model": model}
    resp = forward_ai_request("POST", "/v1/interrogate", files=files, data=data)
    if not (isinstance(resp, tuple) and resp[1] == 503):
        return resp

    image = filters.open_image(io.BytesIO(content))
    return jsonify(filters.procedural_interrogate(image, model))


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
