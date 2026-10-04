# ระบบจัดการบันทึก Prompt รายการโปรด (Bookmark / Favorites)
from __future__ import annotations

from flask import Blueprint, jsonify, request
from flask_jwt_extended import jwt_required

from .extensions import db
from .jobs import current_user_id, error_response
from .models import FavoritePrompt, Job

prompts_blueprint = Blueprint("prompts", __name__)


def parse_favorite_payload(data: dict) -> tuple[str, str, str, list[str]]:
    raw_title = data.get("title")
    if not isinstance(raw_title, str):
        raise ValueError("Title must be a string.")
    title = raw_title.strip()
    if not 1 <= len(title) <= 100:
        raise ValueError("Title must contain between 1 and 100 characters.")

    raw_prompt = data.get("prompt")
    if not isinstance(raw_prompt, str):
        raise ValueError("Prompt must be a string.")
    prompt = raw_prompt.strip()
    if not 1 <= len(prompt) <= 1000:
        raise ValueError("Prompt must contain between 1 and 1000 characters.")

    raw_neg = data.get("negative_prompt", "")
    if not isinstance(raw_neg, str):
        raise ValueError("Negative prompt must be a string.")
    negative_prompt = raw_neg.strip()
    if len(negative_prompt) > 1000:
        raise ValueError("Negative prompt cannot exceed 1000 characters.")

    raw_tags = data.get("tags", [])
    if isinstance(raw_tags, str):
        raw_tags = [t.strip() for t in raw_tags.split(",") if t.strip()]
    if not isinstance(raw_tags, list):
        raise ValueError("Tags must be a list of strings.")
    if len(raw_tags) > 20:
        raise ValueError("At most 20 tags are allowed.")

    parsed_tags = []
    for tag in raw_tags:
        if not isinstance(tag, str):
            raise ValueError("Each tag must be a string.")
        cleaned = tag.strip()
        if not cleaned or len(cleaned) > 50:
            raise ValueError("Tags must be non-empty strings of at most 50 characters.")
        parsed_tags.append(cleaned)

    return title, prompt, negative_prompt, parsed_tags


@prompts_blueprint.post("/favorites")
@jwt_required()
def create_favorite():
    """Save a prompt into the user's favorites list (or bookmark directly from a job history)."""
    data = request.get_json(silent=True) or {}
    if not isinstance(data, dict):
        return error_response("validation_error", "The request body must be a JSON object.", 400)

    # Support bookmarking directly from a past job ID (Star button on frontend)
    job_id = data.get("job_id")
    if job_id:
        job = db.session.scalar(db.select(Job).where(Job.id == str(job_id), Job.user_id == current_user_id()))
        if job is None:
            return error_response("not_found", "The specified job does not exist or belongs to another user.", 404)
        if not data.get("prompt"):
            data["prompt"] = job.prompt
        if "negative_prompt" not in data:
            data["negative_prompt"] = job.negative_prompt
        if not data.get("title"):
            data["title"] = (job.prompt[:40] + "...") if len(job.prompt) > 40 else job.prompt

    try:
        title, prompt, negative_prompt, tags = parse_favorite_payload(data)
    except ValueError as exc:
        return error_response("validation_error", str(exc), 400)

    favorite = FavoritePrompt(
        user_id=current_user_id(),
        title=title,
        prompt=prompt,
        negative_prompt=negative_prompt,
        tags=tags,
    )
    db.session.add(favorite)
    db.session.commit()

    return jsonify({"favorite": favorite.to_dict()}), 201


@prompts_blueprint.get("/favorites")
@jwt_required()
def list_favorites():
    """List all favorite prompts saved by the authenticated user with optional search query & tag filter."""
    statement = (
        db.select(FavoritePrompt)
        .where(FavoritePrompt.user_id == current_user_id())
        .order_by(FavoritePrompt.created_at.desc())
    )
    favorites = db.session.scalars(statement).all()

    query = request.args.get("q", "").strip().lower()
    tag_filter = request.args.get("tag", "").strip().lower()

    filtered = []
    for fav in favorites:
        if query:
            in_title = query in fav.title.lower()
            in_prompt = query in fav.prompt.lower()
            in_tags = any(query in str(t).lower() for t in (fav.tags or []))
            if not (in_title or in_prompt or in_tags):
                continue
        if tag_filter:
            if not any(tag_filter == str(t).lower() for t in (fav.tags or [])):
                continue
        filtered.append(fav.to_dict())

    return jsonify({"favorites": filtered, "count": len(filtered)})


@prompts_blueprint.get("/favorites/<int:favorite_id>")
@jwt_required()
def get_favorite(favorite_id: int):
    """Retrieve a specific favorite prompt owned by the authenticated user."""
    favorite = db.session.scalar(
        db.select(FavoritePrompt).where(
            FavoritePrompt.id == favorite_id,
            FavoritePrompt.user_id == current_user_id(),
        )
    )
    if favorite is None:
        return error_response("not_found", "The requested favorite prompt does not exist.", 404)
    return jsonify({"favorite": favorite.to_dict()})


@prompts_blueprint.put("/favorites/<int:favorite_id>")
@jwt_required()
def update_favorite(favorite_id: int):
    """Update title, prompt, negative_prompt, or tags of an existing favorite bookmark."""
    favorite = db.session.scalar(
        db.select(FavoritePrompt).where(
            FavoritePrompt.id == favorite_id,
            FavoritePrompt.user_id == current_user_id(),
        )
    )
    if favorite is None:
        return error_response("not_found", "The requested favorite prompt does not exist.", 404)

    data = request.get_json(silent=True) or {}
    if not isinstance(data, dict):
        return error_response("validation_error", "The request body must be a JSON object.", 400)

    merged = {
        "title": data.get("title", favorite.title),
        "prompt": data.get("prompt", favorite.prompt),
        "negative_prompt": data.get("negative_prompt", favorite.negative_prompt),
        "tags": data.get("tags", favorite.tags),
    }

    try:
        title, prompt, negative_prompt, tags = parse_favorite_payload(merged)
    except ValueError as exc:
        return error_response("validation_error", str(exc), 400)

    favorite.title = title
    favorite.prompt = prompt
    favorite.negative_prompt = negative_prompt
    favorite.tags = tags
    db.session.commit()

    return jsonify({"favorite": favorite.to_dict(), "message": "Favorite prompt updated successfully."}), 200


@prompts_blueprint.delete("/favorites/<int:favorite_id>")
@jwt_required()
def delete_favorite(favorite_id: int):
    """Delete a favorite prompt owned by the authenticated user."""
    favorite = db.session.scalar(
        db.select(FavoritePrompt).where(
            FavoritePrompt.id == favorite_id,
            FavoritePrompt.user_id == current_user_id(),
        )
    )
    if favorite is None:
        return error_response("not_found", "The requested favorite prompt does not exist.", 404)

    db.session.delete(favorite)
    db.session.commit()
    return jsonify({"message": "Favorite prompt deleted.", "id": favorite_id}), 200
