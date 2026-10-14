from __future__ import annotations

from flask import Blueprint, jsonify, request
from flask_jwt_extended import get_jwt_identity, jwt_required

from .extensions import db
from .models import FavoritePrompt, Job


prompts_blueprint = Blueprint("prompts", __name__)


def error_response(code: str, message: str, status: int):
    return jsonify({"error": {"code": code, "message": message}}), status


def current_user_id() -> int:
    return int(get_jwt_identity())


def parse_tags(value) -> list[str]:
    if value in (None, ""):
        return []
    if not isinstance(value, list):
        raise ValueError("tags must be a list.")
    tags = []
    for tag in value:
        text = str(tag).strip()
        if text:
            tags.append(text)
    return tags[:20]


def title_from_prompt(prompt: str) -> str:
    title = prompt.strip()[:60]
    return title or "Untitled prompt"


@prompts_blueprint.get("/favorites")
@jwt_required()
def list_favorites():
    user_id = current_user_id()
    q = (request.args.get("q") or "").strip().lower()
    tag = (request.args.get("tag") or "").strip().lower()
    favorites = db.session.scalars(
        db.select(FavoritePrompt)
        .where(FavoritePrompt.user_id == user_id)
        .order_by(FavoritePrompt.created_at.desc(), FavoritePrompt.id.desc())
    ).all()
    if q:
        favorites = [fav for fav in favorites if q in fav.title.lower() or q in fav.prompt.lower()]
    if tag:
        favorites = [fav for fav in favorites if tag in {str(item).lower() for item in (fav.tags or [])}]
    return jsonify({"favorites": [fav.to_dict() for fav in favorites], "count": len(favorites)})


@prompts_blueprint.post("/favorites")
@jwt_required()
def create_favorite():
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return error_response("validation_error", "JSON body must be an object.", 400)
    user_id = current_user_id()
    if data.get("job_id"):
        job = db.session.scalar(db.select(Job).where(Job.id == str(data["job_id"]), Job.user_id == user_id))
        if job is None:
            return error_response("job_not_found", "The requested job does not exist.", 404)
        prompt = job.prompt
        negative_prompt = job.negative_prompt or ""
        title = str(data.get("title") or title_from_prompt(prompt)).strip()
    else:
        title = str(data.get("title") or "").strip()
        prompt = str(data.get("prompt") or "").strip()
        negative_prompt = str(data.get("negative_prompt") or "").strip()

    if not title or len(title) > 100:
        return error_response("validation_error", "Title is required and cannot exceed 100 characters.", 400)
    if not prompt:
        return error_response("validation_error", "Prompt is required.", 400)
    try:
        tags = parse_tags(data.get("tags"))
    except ValueError as exc:
        return error_response("validation_error", str(exc), 400)

    favorite = FavoritePrompt(
        user_id=user_id,
        title=title,
        prompt=prompt,
        negative_prompt=negative_prompt,
        tags=tags,
    )
    db.session.add(favorite)
    db.session.commit()
    return jsonify({"favorite": favorite.to_dict()}), 201


@prompts_blueprint.get("/favorites/<int:favorite_id>")
@jwt_required()
def get_favorite(favorite_id: int):
    favorite = db.session.scalar(db.select(FavoritePrompt).where(FavoritePrompt.id == favorite_id, FavoritePrompt.user_id == current_user_id()))
    if favorite is None:
        return error_response("favorite_not_found", "The requested favorite does not exist.", 404)
    return jsonify({"favorite": favorite.to_dict()})


@prompts_blueprint.put("/favorites/<int:favorite_id>")
@jwt_required()
def update_favorite(favorite_id: int):
    favorite = db.session.scalar(db.select(FavoritePrompt).where(FavoritePrompt.id == favorite_id, FavoritePrompt.user_id == current_user_id()))
    if favorite is None:
        return error_response("favorite_not_found", "The requested favorite does not exist.", 404)
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return error_response("validation_error", "JSON body must be an object.", 400)
    if "title" in data:
        title = str(data["title"] or "").strip()
        if not title or len(title) > 100:
            return error_response("validation_error", "Title is required and cannot exceed 100 characters.", 400)
        favorite.title = title
    if "prompt" in data:
        prompt = str(data["prompt"] or "").strip()
        if not prompt:
            return error_response("validation_error", "Prompt is required.", 400)
        favorite.prompt = prompt
    if "negative_prompt" in data:
        favorite.negative_prompt = str(data["negative_prompt"] or "").strip()
    if "tags" in data:
        try:
            favorite.tags = parse_tags(data["tags"])
        except ValueError as exc:
            return error_response("validation_error", str(exc), 400)
    db.session.commit()
    return jsonify({"favorite": favorite.to_dict()})


@prompts_blueprint.delete("/favorites/<int:favorite_id>")
@jwt_required()
def delete_favorite(favorite_id: int):
    favorite = db.session.scalar(db.select(FavoritePrompt).where(FavoritePrompt.id == favorite_id, FavoritePrompt.user_id == current_user_id()))
    if favorite is None:
        return error_response("favorite_not_found", "The requested favorite does not exist.", 404)
    db.session.delete(favorite)
    db.session.commit()
    return jsonify({"id": favorite_id})
