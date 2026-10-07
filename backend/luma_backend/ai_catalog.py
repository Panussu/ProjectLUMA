"""Authenticated Backend facade for AiEngine discovery and model previews."""

from __future__ import annotations

import io
from urllib.parse import quote

import requests
from flask import Blueprint, Response, current_app, jsonify, request, url_for
from flask_jwt_extended import get_jwt_identity, jwt_required, verify_jwt_in_request
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer
from PIL import Image, UnidentifiedImageError

from .jobs import error_response

ai_blueprint = Blueprint("ai", __name__)
CATALOGS = {"models", "loras", "samplers", "schedulers", "settings", "styles"}
PREVIEW_MAX_BYTES = 2 * 1024 * 1024


def ai_url(path: str) -> str:
    return f"{current_app.config['AI_SERVICE_URL'].rstrip('/')}{path}"


def ai_headers() -> dict[str, str]:
    return {"X-LUMA-Service-Token": current_app.config["AI_SERVICE_TOKEN"]}


def ai_timeout() -> tuple[float, float]:
    return current_app.config["AI_CONNECT_TIMEOUT"], current_app.config["AI_METADATA_TIMEOUT"]


def preview_serializer() -> URLSafeTimedSerializer:
    return URLSafeTimedSerializer(current_app.config["SECRET_KEY"], salt="luma-ai-preview")


def valid_name(name: str) -> bool:
    return bool(
        name
        and name not in {".", ".."}
        and len(name) <= 255
        and not any(char in name for char in "/\\")
        and not any(ord(char) < 32 for char in name)
    )


def fetch_json(path: str):
    try:
        response = requests.get(ai_url(path), headers=ai_headers(), timeout=ai_timeout(), allow_redirects=False)
    except requests.Timeout:
        return None, error_response("ai_timeout", "The AI service did not respond in time.", 504)
    except requests.RequestException:
        current_app.logger.exception("AI catalog request failed")
        return None, error_response("ai_unavailable", "The AI service is unavailable.", 503)
    if response.status_code == 404:
        return None, error_response("not_found", "The requested AI option does not exist.", 404)
    if response.status_code != 200:
        return None, error_response("ai_error", f"The AI service returned HTTP {response.status_code}.", 502)
    try:
        data = response.json()
    except ValueError:
        return None, error_response("ai_error", "The AI service returned an invalid response.", 502)
    if not isinstance(data, dict):
        return None, error_response("ai_error", "The AI service returned an invalid response.", 502)
    return data, None


@ai_blueprint.get("/<kind>")
@jwt_required()
def catalog(kind: str):
    if kind not in CATALOGS:
        return error_response("not_found", "The requested AI option does not exist.", 404)
    data, error = fetch_json(f"/v1/{kind}")
    if error:
        return error
    if kind in {"models", "loras"}:
        items = data.get(kind)
        if not isinstance(items, list):
            return error_response("ai_error", "The AI service returned an invalid response.", 502)
        for item in items:
            if (
                isinstance(item, dict)
                and item.get("has_preview")
                and isinstance(item.get("name"), str)
                and valid_name(item["name"])
            ):
                name = item["name"]
                token = preview_serializer().dumps({"kind": "model" if kind == "models" else "lora", "name": name})
                item["preview_url"] = url_for("ai.preview", kind="model" if kind == "models" else "lora", name=name, token=token)
            elif isinstance(item, dict):
                item["preview_url"] = None
    return jsonify(data)


@ai_blueprint.get("/styles/<style_id>")
@jwt_required()
def style_detail(style_id: str):
    if not valid_name(style_id):
        return error_response("validation_error", "Invalid style identifier.", 400)
    data, error = fetch_json(f"/v1/styles/{quote(style_id, safe='')}")
    return error if error else jsonify(data)


@ai_blueprint.get("/queue/status")
@jwt_required()
def queue_status():
    data, error = fetch_json("/v1/queue/status")
    return error if error else jsonify(data)


@ai_blueprint.get("/preview/<kind>/<name>")
def preview(kind: str, name: str):
    if kind not in {"model", "lora"} or not valid_name(name):
        return error_response("not_found", "The requested preview does not exist.", 404)
    verify_jwt_in_request(optional=True)
    if get_jwt_identity() is None:
        token = request.args.get("token", "")
        if not token:
            return error_response("authentication_required", "A bearer token or signed preview link is required.", 401)
        try:
            payload = preview_serializer().loads(token, max_age=current_app.config["MEDIA_TOKEN_MAX_AGE"])
        except SignatureExpired:
            return error_response("preview_link_expired", "This preview link has expired.", 401)
        except BadSignature:
            return error_response("invalid_preview_link", "This preview link is invalid.", 401)
        if payload != {"kind": kind, "name": name}:
            return error_response("invalid_preview_link", "This preview link is invalid.", 401)
    try:
        response = requests.get(ai_url(f"/v1/preview/{kind}/{quote(name, safe='')}"), headers=ai_headers(), timeout=ai_timeout(), allow_redirects=False)
    except requests.Timeout:
        return error_response("ai_timeout", "The AI service did not respond in time.", 504)
    except requests.RequestException:
        current_app.logger.exception("AI preview request failed")
        return error_response("ai_unavailable", "The AI service is unavailable.", 503)
    if response.status_code == 404:
        return error_response("not_found", "The requested preview does not exist.", 404)
    if response.status_code != 200:
        return error_response("ai_error", f"The AI service returned HTTP {response.status_code}.", 502)
    content_type = response.headers.get("Content-Type", "").split(";", 1)[0].lower()
    if content_type not in {"image/png", "image/jpeg"} or len(response.content) > PREVIEW_MAX_BYTES:
        return error_response("ai_error", "The AI service returned an invalid preview.", 502)
    try:
        with Image.open(io.BytesIO(response.content)) as image:
            if image.format not in {"PNG", "JPEG"}:
                raise ValueError("Unsupported preview format")
            if image.width * image.height > current_app.config["MAX_OUTPUT_PIXELS"]:
                raise ValueError("Preview is too large")
            if content_type != ("image/png" if image.format == "PNG" else "image/jpeg"):
                raise ValueError("Preview content type does not match image")
            image.verify()
    except (UnidentifiedImageError, OSError, ValueError, Image.DecompressionBombError):
        return error_response("ai_error", "The AI service returned an invalid preview.", 502)
    result = Response(response.content, content_type=content_type)
    result.headers["Cache-Control"] = "private, max-age=3600"
    return result
