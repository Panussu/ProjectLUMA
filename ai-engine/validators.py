# กฎตรวจสอบข้อมูลและโครงสร้างคำขอสร้างภาพสำหรับ LUMA AI Engine
"""Validation utilities and request models for LUMA AI Engine."""

from __future__ import annotations

import hashlib
from typing import Any

from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel, field_validator

MAX_DIMENSION = 1024
MIN_DIMENSION = 256
MAX_PROMPT_LENGTH = 1000


# จัดรูปข้อผิดพลาดให้มี code และ message พร้อมรหัสสถานะ HTTP
def error_response(code: str, message: str, status: int) -> JSONResponse:
    return JSONResponse({"error": {"code": code, "message": message}}, status_code=status)


# แปลงและตรวจค่าตัวเลขกับช่วงที่อนุญาตก่อนนำไปใช้งาน
def parse_integer(value: Any, name: str, minimum: int, maximum: int) -> int:
    if isinstance(value, bool):
        raise ValueError(f"{name} must be an integer.")
    try:
        parsed = int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{name} must be an integer.") from exc
    if not minimum <= parsed <= maximum:
        raise ValueError(f"{name} must be between {minimum} and {maximum}.")
    return parsed


# เตรียมข้อความคำสั่งและตรวจความยาวก่อนส่งเข้ากระบวนการภาพ
def parse_prompt(value: Any) -> str:
    prompt = str(value or "").strip()
    if not 3 <= len(prompt) <= MAX_PROMPT_LENGTH:
        raise ValueError("Prompt must contain between 3 and 1000 characters.")
    return prompt


# ใช้ seed ที่ส่งมา หรือคำนวณจากแฮช prompt เมื่อไม่ได้ระบุ
def prompt_seed(prompt: str, supplied_seed: Any = None) -> int:
    if supplied_seed not in (None, ""):
        return parse_integer(supplied_seed, "seed", 0, 4_294_967_295)
    digest = hashlib.sha256(prompt.encode("utf-8")).digest()
    return int.from_bytes(digest[:4], "big")


# ดึงข้อความจากข้อผิดพลาดตรวจข้อมูลของ FastAPI ให้ใช้รูปแบบเดียวกับ API
def validation_message(error: RequestValidationError) -> str:
    if not error.errors():
        return "The request is invalid."
    detail = error.errors()[0]
    context_error = detail.get("ctx", {}).get("error")
    message = str(context_error or detail.get("msg") or "The request is invalid.")
    return message.removeprefix("Value error, ")


# โครงสร้างคำขอสร้างภาพและกฎตรวจข้อมูลก่อนเข้า endpoint
class GenerateRequest(BaseModel):
    """Validated request body for image generation."""

    prompt: str
    negative_prompt: str = ""
    width: int = 512
    height: int = 512
    seed: int | None = None
    steps: int = 20
    model: str | None = None
    loras: list | None = None
    sampler: str | None = None
    scheduler: str | None = None
    cfg_scale: float | None = None
    clip_skip: int | None = None
    style_preset: str | None = None

    # ตรวจ prompt ผ่านกฎกลางก่อนสร้างโมเดลคำขอ
    @field_validator("prompt", mode="before")
    @classmethod
    def validate_prompt(cls, value: Any) -> str:
        return parse_prompt(value)

    # เตรียม negative prompt และจำกัดความยาว
    @field_validator("negative_prompt", mode="before")
    @classmethod
    def validate_negative_prompt(cls, value: Any) -> str:
        negative_prompt = str(value or "").strip()
        if len(negative_prompt) > MAX_PROMPT_LENGTH:
            raise ValueError("Negative prompt cannot exceed 1000 characters.")
        return negative_prompt

    # ตรวจขนาดภาพให้อยู่ในช่วงและหารด้วย 64 ลงตัว
    @field_validator("width", "height", mode="before")
    @classmethod
    def validate_dimension(cls, value: Any, info) -> int:
        dimension = parse_integer(value, info.field_name, MIN_DIMENSION, MAX_DIMENSION)
        if dimension % 64:
            raise ValueError("Width and height must be divisible by 64.")
        return dimension

    # อนุญาตค่า seed ว่าง หรือจำนวนเต็มในช่วง 32 บิตไม่ติดลบ
    @field_validator("seed", mode="before")
    @classmethod
    def validate_seed(cls, value: Any) -> int | None:
        if value in (None, ""):
            return None
        return parse_integer(value, "seed", 0, 4_294_967_295)

    # ตรวจจำนวนขั้นการสร้างภาพให้อยู่ระหว่าง 1 ถึง 50
    @field_validator("steps", mode="before")
    @classmethod
    def validate_steps(cls, value: Any) -> int:
        return parse_integer(value, "steps", 1, 50)

    @field_validator("model", mode="before")
    @classmethod
    def validate_model(cls, value: Any) -> str | None:
        if value in (None, ""):
            return None
        return str(value).strip()

    @field_validator("sampler", mode="before")
    @classmethod
    def validate_sampler(cls, value: Any) -> str | None:
        if value in (None, ""):
            return None
        return str(value).strip()

    @field_validator("scheduler", mode="before")
    @classmethod
    def validate_scheduler(cls, value: Any) -> str | None:
        if value in (None, ""):
            return None
        return str(value).strip()

    @field_validator("cfg_scale", mode="before")
    @classmethod
    def validate_cfg_scale(cls, value: Any) -> float | None:
        if value in (None, ""):
            return None
        try:
            val = float(value)
        except (ValueError, TypeError) as exc:
            raise ValueError("cfg_scale must be a number.") from exc
        if not 1.0 <= val <= 30.0:
            raise ValueError("cfg_scale must be between 1.0 and 30.0.")
        return val

    @field_validator("clip_skip", mode="before")
    @classmethod
    def validate_clip_skip(cls, value: Any) -> int | None:
        if value in (None, ""):
            return None
        try:
            val = int(value)
        except (ValueError, TypeError) as exc:
            raise ValueError("clip_skip must be an integer.") from exc
        if not 1 <= val <= 12:
            raise ValueError("clip_skip must be between 1 and 12.")
        return val

    @field_validator("style_preset", mode="before")
    @classmethod
    def validate_style_preset(cls, value: Any) -> str | None:
        if value in (None, ""):
            return None
        return str(value).strip()
