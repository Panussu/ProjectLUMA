from __future__ import annotations

from datetime import datetime, timezone
import json
import math
import re
import secrets
import uuid
from pathlib import Path

import requests
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


def error_response(code: str, message: str, status: int):
    return jsonify({"error": {"code": code, "message": message}}), status


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


def parse_prompt(value) -> str:
    if not isinstance(value, str):
        raise ValueError("Prompt must be a string.")
    prompt = value.strip()
    if not 3 <= len(prompt) <= 1000:
        raise ValueError("Prompt must contain between 3 and 1000 characters.")
    return prompt


def parse_ai_options(data: dict) -> dict:
    options: dict = {}
    for key in ("model", "sampler", "scheduler", "style_preset"):
        value = data.get(key)
        if value in (None, ""):
            continue
        if not isinstance(value, str):
            raise ValueError(f"{key} must be a string.")
        value = value.strip()
        if len(value) > 255:
            raise ValueError(f"{key} cannot exceed 255 characters.")
        if value:
            options[key] = value

    loras = data.get("loras")
    if loras not in (None, ""):
        if isinstance(loras, str):
            try:
                loras = json.loads(loras)
            except ValueError as exc:
                raise ValueError("loras must be a JSON list.") from exc
        if not isinstance(loras, list) or len(loras) > 8:
            raise ValueError("loras must be a list of at most 8 items.")
        parsed_loras = []
        for item in loras:
            if isinstance(item, str):
                name = item.strip()
                parsed = name
            elif isinstance(item, dict):
                name = str(item.get("name", "")).strip()
                weight = float(item.get("weight", 1.0))
                if not math.isfinite(weight) or not 0 <= weight <= 2:
                    raise ValueError("LoRA weight must be between 0 and 2.")
                parsed = {"name": name, "weight": weight}
            else:
                raise ValueError("loras entries must be strings or objects.")
            if not name:
                raise ValueError("LoRA name is required.")
            parsed_loras.append(parsed)
        options["loras"] = parsed_loras

    if data.get("cfg_scale") not in (None, ""):
        cfg_scale = float(data["cfg_scale"])
        if not math.isfinite(cfg_scale) or not 1 <= cfg_scale <= 30:
            raise ValueError("cfg_scale must be between 1 and 30.")
        options["cfg_scale"] = cfg_scale

    if data.get("clip_skip") not in (None, ""):
        clip_skip = parse_integer(data["clip_skip"], "clip_skip", 1, 12)
        options["clip_skip"] = clip_skip

    return options


def current_user_id() -> int:
    return int(get_jwt_identity())


def serializer() -> URLSafeTimedSerializer:
    return URLSafeTimedSerializer(current_app.config["SECRET_KEY"], salt="luma-media")


def result_url(job: Job) -> str | None:
    if job.status != "completed" or not job.result_filename:
        return None
    token = serializer().dumps({"job": job.id, "user": job.user_id, "file": job.result_filename})
    return f"/media/{job.result_filename}?token={token}"


def serialized(job: Job) -> dict:
    return job.to_dict(result_url(job))


@jobs_blueprint.post("/generate")
@jwt_required()
def generate():
    data = request.get_json(silent=True) or {}
    try:
        prompt = parse_prompt(data.get("prompt"))
        negative_prompt = str(data.get("negative_prompt", "")).strip()
        if len(negative_prompt) > 1000:
            raise ValueError("Negative prompt cannot exceed 1000 characters.")
        width = parse_integer(data.get("width", 512), "width", 256, 1536)
        height = parse_integer(data.get("height", 512), "height", 256, 1536)
        if width % 64 or height % 64:
            raise ValueError("Width and height must be divisible by 64.")
        steps = parse_integer(data.get("steps", 20), "steps", 1, 150)
        seed = parse_integer(data.get("seed", secrets.randbits(32)), "seed", 0, 4_294_967_295)
        ai_options = parse_ai_options(data)
    except ValueError as exc:
        return error_response("validation_error", str(exc), 400)

    job = Job(
        user_id=current_user_id(),
        type="generate",
        prompt=prompt,
        negative_prompt=negative_prompt,
        width=width,
        height=height,
        steps=steps,
        seed=seed,
        model=ai_options.get("model"),
        loras=json.dumps(ai_options["loras"]) if "loras" in ai_options else None,
        sampler=ai_options.get("sampler"),
        scheduler=ai_options.get("scheduler"),
        cfg_scale=ai_options.get("cfg_scale"),
        clip_skip=ai_options.get("clip_skip"),
        style_preset=ai_options.get("style_preset"),
    )
    db.session.add(job)
    db.session.add(JobAIOptions(job=job, request_options=ai_options))
    db.session.commit()
    response = serialized(job)
    queue_job(current_app._get_current_object(), job.id)
    return jsonify({"job": response}), 202


@jobs_blueprint.post("/edit")
@jwt_required()
def edit():
    upload = request.files.get("image")
    if upload is None or not upload.filename:
        return error_response("validation_error", "An image file is required.", 400)
    try:
        prompt = parse_prompt(request.form.get("prompt"))
        strength = float(request.form.get("strength", "0.65"))
        if not 0 <= strength <= 1:
            raise ValueError("Strength must be between 0 and 1.")
        seed = parse_integer(request.form.get("seed", secrets.randbits(32)), "seed", 0, 4_294_967_295)
        ai_options = parse_ai_options(request.form.to_dict())

        image = Image.open(upload.stream)
        image.verify()
        if image.format not in ALLOWED_FORMATS:
            raise ValueError("Only PNG, JPEG, and WebP images are accepted.")
        upload.stream.seek(0)
        image = Image.open(upload.stream)
        if image.width * image.height > 4_194_304:
            raise ValueError("The input image has too many pixels.")
        upload.stream.seek(0)
    except (ValueError, UnidentifiedImageError) as exc:
        return error_response("validation_error", str(exc) or "The uploaded file is not a valid image.", 400)

    source_filename = f"{uuid.uuid4()}.{image.format.lower().replace('jpeg', 'jpg')}"
    source_path = Path(current_app.config["UPLOAD_ROOT"]) / source_filename
    upload.save(source_path)
    job = Job(
        user_id=current_user_id(),
        type="edit",
        prompt=prompt,
        strength=strength,
        seed=seed,
        source_filename=source_filename,
        model=ai_options.get("model"),
        loras=json.dumps(ai_options["loras"]) if "loras" in ai_options else None,
        sampler=ai_options.get("sampler"),
        scheduler=ai_options.get("scheduler"),
        cfg_scale=ai_options.get("cfg_scale"),
        clip_skip=ai_options.get("clip_skip"),
        style_preset=ai_options.get("style_preset"),
    )
    db.session.add(job)
    db.session.add(JobAIOptions(job=job, request_options=ai_options))
    db.session.commit()
    response = serialized(job)
    queue_job(current_app._get_current_object(), job.id)
    return jsonify({"job": response}), 202


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


@jobs_blueprint.get("/<job_id>")
@jwt_required()
def get_job(job_id: str):
    job = db.session.scalar(db.select(Job).where(Job.id == job_id, Job.user_id == current_user_id()))
    if job is None:
        return error_response("job_not_found", "The requested job does not exist.", 404)
    return jsonify({"job": serialized(job)})


def ai_headers() -> dict[str, str]:
    return {"X-LUMA-Service-Token": current_app.config["AI_SERVICE_TOKEN"]}


def ai_url(path: str) -> str:
    return f"{current_app.config['AI_SERVICE_URL'].rstrip('/')}{path}"


@jobs_blueprint.get("/progress")
@jwt_required()
def overall_progress():
    include_preview = request.args.get("include_preview", "false")
    try:
        response = requests.get(
            ai_url("/v1/progress"),
            headers=ai_headers(),
            params={"include_preview": include_preview},
            timeout=(current_app.config["AI_CONNECT_TIMEOUT"], current_app.config["AI_READ_TIMEOUT"]),
        )
        if response.ok:
            return jsonify(response.json())
    except requests.RequestException:
        current_app.logger.info("AI progress endpoint unavailable", exc_info=True)
    return jsonify({"status": "unavailable", "active": False, "progress_percent": 0.0})


@jobs_blueprint.get("/<job_id>/progress")
@jwt_required()
def job_progress(job_id: str):
    job = db.session.scalar(db.select(Job).where(Job.id == job_id, Job.user_id == current_user_id()))
    if job is None:
        return error_response("job_not_found", "The requested job does not exist.", 404)
    if job.status == "completed":
        return jsonify({"job_id": job.id, "status": job.status, "progress_percent": 100.0})
    if job.status == "queued":
        return jsonify({"job_id": job.id, "status": job.status, "progress_percent": 0.0})
    if job.status in {"failed", "cancelled", "interrupted"}:
        return jsonify({"job_id": job.id, "status": job.status, "progress_percent": float(job.progress or 0), "error": job.error})

    data = overall_progress().get_json() or {}
    data["job_id"] = job.id
    data["status"] = job.status
    data.setdefault("progress_percent", float(job.progress or 0))
    return jsonify(data)


@jobs_blueprint.post("/<job_id>/cancel")
@jwt_required()
def cancel_job(job_id: str):
    job = db.session.scalar(db.select(Job).where(Job.id == job_id, Job.user_id == current_user_id()))
    if job is None:
        return error_response("job_not_found", "The requested job does not exist.", 404)
    if job.status in {"cancelled", "completed", "failed", "interrupted"}:
        return error_response("job_not_cancellable", "This job cannot be cancelled.", 409)
    if job.status == "processing":
        try:
            requests.post(
                ai_url("/v1/interrupt"),
                headers=ai_headers(),
                timeout=(current_app.config["AI_CONNECT_TIMEOUT"], current_app.config["AI_METADATA_TIMEOUT"]),
            )
        except requests.RequestException:
            current_app.logger.info("AI interrupt endpoint unavailable", exc_info=True)
    job.status = "cancelled"
    job.error = "Generation cancelled by user."
    job.progress = 0
    job.completed_at = datetime.now(timezone.utc)
    db.session.commit()
    return jsonify({"job": serialized(job), "status": "cancelled"})


@media_blueprint.get("/<path:filename>")
def media(filename: str):
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

    token = request.args.get("token", "")
    if not token:
        return error_response(
            "authentication_required",
            "A bearer token or signed media link is required.",
            401,
        )

    keys_to_try = [
        current_app.config.get("SECRET_KEY", "development-secret-change-me"),
        "development-secret-change-me",
        "replace-with-a-long-random-value",
    ]
    payload = None
    expired = False
    for k in keys_to_try:
        try:
            payload = URLSafeTimedSerializer(k, salt="luma-media").loads(
                token, max_age=current_app.config.get("MEDIA_TOKEN_MAX_AGE", 3600)
            )
            break
        except SignatureExpired:
            expired = True
        except BadSignature:
            continue

    if payload is None:
        if expired:
            return error_response("media_link_expired", "This image link has expired. Refresh the job to receive a new link.", 401)
        return error_response("invalid_media_link", "This image link is invalid.", 401)

    if payload.get("file") != filename:
        current_app.logger.warning("Media filename mismatch: payload=%r, filename=%r", payload.get("file"), filename)
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


def send_media_file(filename: str):
    as_download = request.args.get("download") == "1"
    response = send_from_directory(
        current_app.config["MEDIA_ROOT"],
        filename,
        conditional=True,
        as_attachment=as_download,
        download_name=filename if as_download else None,
    )
    response.headers["Cache-Control"] = "private, max-age=3600"
    response.headers["Access-Control-Allow-Origin"] = "*"
    return response

