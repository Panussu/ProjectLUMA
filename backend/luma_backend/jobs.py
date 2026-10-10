from __future__ import annotations

from datetime import datetime, timezone
import json
import secrets
import uuid
from pathlib import Path

from flask import Blueprint, current_app, jsonify, request, send_from_directory
from flask_jwt_extended import get_jwt_identity, jwt_required, verify_jwt_in_request
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer
from PIL import Image, UnidentifiedImageError

from .extensions import db
from .models import Job
from .worker import queue_job

jobs_blueprint = Blueprint("jobs", __name__)
media_blueprint = Blueprint("media", __name__)
ALLOWED_FORMATS = {"PNG", "JPEG", "WEBP"}


def error_response(code: str, message: str, status: int):
    return jsonify({"error": {"code": code, "message": message}}), status


def parse_integer(value, name: str, minimum: int, maximum: int) -> int:
    if isinstance(value, bool):
        raise ValueError(f"{name} must be an integer.")
    try:
        parsed = int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{name} must be an integer.") from exc
    if not minimum <= parsed <= maximum:
        raise ValueError(f"{name} must be between {minimum} and {maximum}.")
    return parsed


def parse_prompt(value) -> str:
    prompt = str(value or "").strip()
    if not 3 <= len(prompt) <= 1000:
        raise ValueError("Prompt must contain between 3 and 1000 characters.")
    return prompt


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
        model = str(data.get("model", "")).strip() or None
        raw_loras = data.get("loras")
        if isinstance(raw_loras, (list, dict)):
            loras = json.dumps(raw_loras)
        elif raw_loras:
            loras = str(raw_loras).strip()
        else:
            loras = None
        sampler = str(data.get("sampler", "")).strip() or None
        scheduler = str(data.get("scheduler", "")).strip() or None
        cfg_scale = float(data["cfg_scale"]) if data.get("cfg_scale") not in (None, "") else None
        clip_skip = int(data["clip_skip"]) if data.get("clip_skip") not in (None, "") else None
        style_preset = str(data.get("style_preset", "")).strip() or None
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
        model=model,
        loras=loras,
        sampler=sampler,
        scheduler=scheduler,
        cfg_scale=cfg_scale,
        clip_skip=clip_skip,
        style_preset=style_preset,
    )
    db.session.add(job)
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
        model = str(request.form.get("model", "")).strip() or None
        raw_loras = request.form.get("loras")
        loras = str(raw_loras).strip() if raw_loras else None
        sampler = str(request.form.get("sampler", "")).strip() or None
        scheduler = str(request.form.get("scheduler", "")).strip() or None
        cfg_scale = float(request.form["cfg_scale"]) if request.form.get("cfg_scale") not in (None, "") else None
        clip_skip = int(request.form["clip_skip"]) if request.form.get("clip_skip") not in (None, "") else None
        style_preset = str(request.form.get("style_preset", "")).strip() or None

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
        model=model,
        loras=loras,
        sampler=sampler,
        scheduler=scheduler,
        cfg_scale=cfg_scale,
        clip_skip=clip_skip,
        style_preset=style_preset,
    )
    db.session.add(job)
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


@jobs_blueprint.post("/<job_id>/cancel")
@jwt_required()
def cancel_job(job_id: str):
    job = db.session.scalar(db.select(Job).where(Job.id == job_id, Job.user_id == current_user_id()))
    if job is None:
        return error_response("job_not_found", "The requested job does not exist.", 404)
    job.status = "interrupted"
    job.error = "Generation interrupted by user."
    job.progress = 0
    job.completed_at = datetime.now(timezone.utc)
    db.session.commit()
    return jsonify({"job": serialized(job), "status": "interrupted"})


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

