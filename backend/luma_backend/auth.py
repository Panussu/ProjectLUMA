# จัดการสมัครสมาชิก เข้าสู่ระบบ และอ่านผู้ใช้จาก JWT
from __future__ import annotations

import re

from flask import Blueprint, jsonify, request
from flask_jwt_extended import create_access_token, get_jwt_identity, jwt_required
from sqlalchemy.exc import IntegrityError

from .extensions import db
from .models import User

auth_blueprint = Blueprint("auth", __name__)
USERNAME_PATTERN = re.compile(r"^[a-z0-9_.-]{3,40}$")


# จัดรูปข้อผิดพลาดให้มี code และ message พร้อมรหัสสถานะ HTTP
def error_response(code: str, message: str, status: int):
    return jsonify({"error": {"code": code, "message": message}}), status


# อ่านข้อมูลเข้าสู่ระบบและปรับชื่อผู้ใช้ให้เปรียบเทียบได้โดยไม่สนตัวพิมพ์
def credentials_from_request() -> tuple[str, str]:
    data = request.get_json(silent=True) or {}
    username = str(data.get("username", "")).strip().casefold()
    password = str(data.get("password", ""))
    return username, password


# ตรวจชื่อและรหัสผ่าน เก็บค่าแฮช แล้วออก JWT ให้บัญชีใหม่
@auth_blueprint.post("/register")
def register():
    username, password = credentials_from_request()
    if not USERNAME_PATTERN.fullmatch(username):
        return error_response("validation_error", "Username must be 3-40 characters using letters, numbers, _, ., or -.", 400)
    if not 8 <= len(password) <= 128:
        return error_response("validation_error", "Password must contain between 8 and 128 characters.", 400)

    # เก็บรหัสผ่านเป็นแฮชก่อนบันทึกบัญชี

    user = User(username=username)
    user.set_password(password)
    db.session.add(user)
    try:
        db.session.commit()
    # ย้อนธุรกรรมเมื่อชื่อชนกันแล้วตอบสถานะ 409
    except IntegrityError:
        db.session.rollback()
        return error_response("username_taken", "That username is already registered.", 409)

    # ออก JWT โดยผูก identity กับ ID ของผู้ใช้

    token = create_access_token(identity=str(user.id))
    return jsonify({"access_token": token, "user": user.to_dict()}), 201


# ค้นหาบัญชี ตรวจค่าแฮชรหัสผ่าน และออกโทเคนเมื่อข้อมูลถูกต้อง
@auth_blueprint.post("/login")
def login():
    username, password = credentials_from_request()
    user = db.session.scalar(db.select(User).where(User.username == username))
    if user is None or not user.check_password(password):
        return error_response("invalid_credentials", "The username or password is incorrect.", 401)
    token = create_access_token(identity=str(user.id))
    return jsonify({"access_token": token, "user": user.to_dict()})


# อ่านผู้ใช้จากตัวตนใน JWT โดยไม่ส่งค่าแฮชรหัสผ่านกลับ
@auth_blueprint.get("/me")
@jwt_required()
def me():
    user = db.session.get(User, int(get_jwt_identity()))
    if user is None:
        return error_response("user_not_found", "The account no longer exists.", 404)
    return jsonify({"user": user.to_dict()})

