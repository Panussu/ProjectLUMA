from __future__ import annotations

import re

from flask import Blueprint, jsonify, request
from flask_jwt_extended import create_access_token, get_jwt_identity, jwt_required
from sqlalchemy.exc import IntegrityError

from .extensions import db
from .models import User

auth_blueprint = Blueprint("auth", __name__)
USERNAME_PATTERN = re.compile(r"^[a-z0-9_.-]{3,40}$")


def error_response(code: str, message: str, status: int):
    return jsonify({"error": {"code": code, "message": message}}), status


def credentials_from_request() -> tuple[str, str]:
    data = request.get_json(silent=True) or {}
    username = str(data.get("username", "")).strip().casefold()
    password = str(data.get("password", ""))
    return username, password


@auth_blueprint.post("/register")
def register():
    username, password = credentials_from_request()
    if not USERNAME_PATTERN.fullmatch(username):
        return error_response("validation_error", "Username must be 3-40 characters using letters, numbers, _, ., or -.", 400)
    if not 8 <= len(password) <= 128:
        return error_response("validation_error", "Password must contain between 8 and 128 characters.", 400)

    user = User(username=username)
    user.set_password(password)
    db.session.add(user)
    try:
        db.session.commit()
    except IntegrityError:
        db.session.rollback()
        return error_response("username_taken", "That username is already registered.", 409)

    token = create_access_token(identity=str(user.id))
    return jsonify({"access_token": token, "user": user.to_dict()}), 201


@auth_blueprint.post("/login")
def login():
    username, password = credentials_from_request()
    user = db.session.scalar(db.select(User).where(User.username == username))
    if user is None or not user.check_password(password):
        return error_response("invalid_credentials", "The username or password is incorrect.", 401)
    token = create_access_token(identity=str(user.id))
    return jsonify({"access_token": token, "user": user.to_dict()})


@auth_blueprint.get("/me")
@jwt_required()
def me():
    user = db.session.get(User, int(get_jwt_identity()))
    if user is None:
        return error_response("user_not_found", "The account no longer exists.", 404)
    return jsonify({"user": user.to_dict()})

