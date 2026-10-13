from __future__ import annotations

from urllib.parse import quote

import requests
from flask import Blueprint, Response, current_app, jsonify, request, url_for
from flask_jwt_extended import jwt_required, verify_jwt_in_request
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer


ai_catalog_blueprint = Blueprint("ai_catalog", __name__)


def ai_headers() -> dict[str, str]:
    return {"X-LUMA-Service-Token": current_app.config["AI_SERVICE_TOKEN"]}


def ai_timeout():
    return (current_app.config["AI_CONNECT_TIMEOUT"], current_app.config["AI_METADATA_TIMEOUT"])


def ai_url(path: str) -> str:
    return f"{current_app.config['AI_SERVICE_URL'].rstrip('/')}{path}"


def preview_serializer() -> URLSafeTimedSerializer:
    return URLSafeTimedSerializer(current_app.config["SECRET_KEY"], salt="luma-ai-preview")


def forward_engine_json(engine_path: str):
    try:
        response = requests.get(ai_url(f"/v1/{engine_path}"), headers=ai_headers(), timeout=ai_timeout())
    except requests.RequestException:
        return jsonify({"error": {"code": "ai_service_unavailable", "message": "The AI service is currently unreachable."}}), 503
    if not response.ok:
        return jsonify({"error": {"code": "ai_error", "message": "The AI service could not complete the request."}}), 502
    try:
        return jsonify(response.json()), response.status_code
    except ValueError:
        return jsonify({"error": {"code": "ai_error", "message": "The AI service returned an invalid response."}}), 502


def catalog_with_signed_previews(engine_path: str, collection_key: str, preview_kind: str | None = None):
    result = forward_engine_json(engine_path)
    response = result[0] if isinstance(result, tuple) else result
    if getattr(response, "status_code", 200) >= 400:
        return result
    payload = response.get_json() or {}
    if preview_kind and isinstance(payload.get(collection_key), list):
        for item in payload[collection_key]:
            name = item.get("name")
            if name and item.get("has_preview"):
                token = preview_serializer().dumps({"kind": preview_kind, "name": name})
                item["preview_url"] = url_for("ai_catalog.preview", kind=preview_kind, name=name, token=token)
    return jsonify(payload)


@ai_catalog_blueprint.get("/models")
@jwt_required()
def models():
    return catalog_with_signed_previews("models", "models", "model")


@ai_catalog_blueprint.get("/loras")
@jwt_required()
def loras():
    return catalog_with_signed_previews("loras", "loras", "lora")


@ai_catalog_blueprint.get("/samplers")
@jwt_required()
def samplers():
    return forward_engine_json("samplers")


@ai_catalog_blueprint.get("/schedulers")
@jwt_required()
def schedulers():
    return forward_engine_json("schedulers")


@ai_catalog_blueprint.get("/settings")
@jwt_required()
def settings():
    return forward_engine_json("settings")


@ai_catalog_blueprint.get("/styles")
@jwt_required()
def styles():
    return forward_engine_json("styles")


@ai_catalog_blueprint.get("/styles/<style_id>")
@jwt_required()
def style(style_id: str):
    return forward_engine_json(f"styles/{style_id}")


@ai_catalog_blueprint.get("/queue/status")
@jwt_required()
def queue_status():
    return forward_engine_json("queue/status")


@ai_catalog_blueprint.get("/preview/<kind>/<path:name>")
def preview(kind: str, name: str):
    if kind not in {"model", "lora"}:
        return jsonify({"error": {"code": "not_found", "message": "The requested preview does not exist."}}), 404
    try:
        verify_jwt_in_request(optional=True)
    except Exception:
        pass
    token = request.args.get("token", "")
    if token:
        try:
            payload = preview_serializer().loads(token, max_age=current_app.config["MEDIA_TOKEN_MAX_AGE"])
        except SignatureExpired:
            return jsonify({"error": {"code": "preview_link_expired", "message": "This preview link has expired."}}), 401
        except BadSignature:
            return jsonify({"error": {"code": "invalid_preview_link", "message": "This preview link is invalid."}}), 401
        if payload.get("kind") != kind or payload.get("name") != name:
            return jsonify({"error": {"code": "invalid_preview_link", "message": "This preview link is invalid."}}), 401
    else:
        try:
            verify_jwt_in_request()
        except Exception:
            return jsonify({"error": {"code": "authentication_required", "message": "A bearer token or signed preview link is required."}}), 401

    try:
        response = requests.get(
            ai_url(f"/v1/preview/{kind}/{quote(name, safe='')}"),
            headers=ai_headers(),
            timeout=ai_timeout(),
        )
    except requests.RequestException:
        return jsonify({"error": {"code": "ai_service_unavailable", "message": "The AI service is currently unreachable."}}), 503
    if not response.ok:
        return jsonify({"error": {"code": "not_found", "message": "The requested preview does not exist."}}), 404
    content_type = response.headers.get("Content-Type", "")
    if "image/" not in content_type:
        return jsonify({"error": {"code": "ai_error", "message": "The AI service returned an invalid preview."}}), 502
    return Response(response.content, content_type=content_type)
