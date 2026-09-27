# บริการ FastAPI เชื่อม Forge และ provider ภาพทดสอบ
"""Private LUMA image service with WebUI Forge and development providers."""

from __future__ import annotations

import base64
import hashlib
import io
import json
import logging
import os
import random
import textwrap
import threading
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Annotated, Any

import requests
from dotenv import load_dotenv
from fastapi import Depends, FastAPI, File, Form, Header, Request, UploadFile
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse, Response
from PIL import Image, ImageChops, ImageDraw, ImageEnhance, ImageFilter, ImageFont, ImageOps, UnidentifiedImageError
from pydantic import BaseModel, field_validator
from starlette.exceptions import HTTPException as StarletteHTTPException

# โหลดค่าจาก .env ก่อนสร้างแอปหรืออ่าน environment

load_dotenv()

MAX_DIMENSION = 1024
MIN_DIMENSION = 256
MAX_PROMPT_LENGTH = 1000


# ข้อผิดพลาดจากคำตอบของบริการสร้างภาพ
class ProviderError(RuntimeError):
    """The configured image provider returned an invalid response."""


# ข้อผิดพลาดเมื่อไม่สามารถเชื่อมต่อบริการสร้างภาพได้
class ProviderUnavailable(ProviderError):
    """The configured image provider could not be reached."""


# ข้อผิดพลาดที่กำหนด code ข้อความ และ HTTP status สำหรับ API ภายใน
class ApiError(RuntimeError):
    """A stable error response returned by the private LUMA API."""

    # กำหนดค่าเริ่มต้นของออบเจ็กต์จากพารามิเตอร์หรือค่ากำหนดที่ใช้ในคลาสนี้
    def __init__(self, code: str, message: str, status_code: int):
        super().__init__(message)
        self.code = code
        self.message = message
        self.status_code = status_code


# ระบบจัดการคิวและควบคุมการประมวลผลพร้อมกันสำหรับ GPU (Concurrency & Queue Manager)
class GenerationQueueManager:
    """Thread-safe concurrency limiter and request queue for AI image generation."""

    def __init__(self, max_concurrency: int = 1, max_capacity: int = 20, default_timeout: float = 180.0):
        self.max_concurrency = max(1, int(max_concurrency))
        self.max_capacity = max(1, int(max_capacity))
        self.default_timeout = max(1.0, float(default_timeout))
        self._semaphore = threading.Semaphore(self.max_concurrency)
        self._lock = threading.Lock()
        self._active_jobs = 0
        self._queued_jobs = 0
        self._total_completed = 0
        self._total_failed = 0
        self._total_rejected = 0
        self._total_wait_time_ms = 0.0
        self._total_exec_time_ms = 0.0
        self._start_time = time.time()
        self._active_job_start: float = 0.0

    @property
    def active_jobs(self) -> int:
        with self._lock:
            return self._active_jobs

    @property
    def queued_jobs(self) -> int:
        with self._lock:
            return self._queued_jobs

    def status(self) -> dict[str, Any]:
        with self._lock:
            completed = self._total_completed
            avg_exec = round(self._total_exec_time_ms / completed, 1) if completed > 0 else 0.0
            avg_wait = round(self._total_wait_time_ms / completed, 1) if completed > 0 else 0.0
            estimated_wait_sec = round(self._queued_jobs * (avg_exec / 1000.0), 1) if avg_exec > 0 else 0.0
            return {
                "status": "ok",
                "gpu_available": self._active_jobs < self.max_concurrency,
                "active_jobs": self._active_jobs,
                "queued_jobs": self._queued_jobs,
                "max_concurrency": self.max_concurrency,
                "queue_capacity": self.max_capacity,
                "total_completed": self._total_completed,
                "total_failed": self._total_failed,
                "total_rejected": self._total_rejected,
                "average_execution_time_ms": avg_exec,
                "average_wait_time_ms": avg_wait,
                "estimated_wait_time_seconds": estimated_wait_sec,
                "uptime_seconds": round(time.time() - self._start_time, 1),
            }

    def live_progress_simulation(self, default_steps: int = 20, include_preview: bool = False) -> dict[str, Any]:
        with self._lock:
            active = self._active_jobs > 0
            start_ts = self._active_job_start
            completed = self._total_completed
            total_exec = self._total_exec_time_ms

        if not active or start_ts <= 0.0:
            return {
                "active": False,
                "progress": 0.0,
                "progress_percent": 0.0,
                "sampling_step": 0,
                "sampling_steps": 0,
                "eta_relative": 0.0,
                "interrupted": False,
                "preview_image": None,
                "preview_available": False,
            }

        elapsed = max(0.001, time.perf_counter() - start_ts)
        avg_exec_sec = (total_exec / completed / 1000.0) if completed > 0 else 2.5
        avg_exec_sec = max(0.5, avg_exec_sec)

        ratio = elapsed / avg_exec_sec
        if ratio < 1.0:
            progress = min(0.95, max(0.05, ratio))
        else:
            progress = min(0.98, 0.95 + 0.03 * (1.0 - (1.0 / (1.0 + (ratio - 1.0)))))

        total_steps = max(1, default_steps)
        current_step = min(total_steps, max(1, int(round(progress * total_steps))))
        eta = max(0.0, round(avg_exec_sec - elapsed, 1)) if elapsed < avg_exec_sec else 0.5

        preview_b64 = None
        if include_preview:
            try:
                preview_img = Image.new("RGB", (64, 64), color=(30, 32, 48))
                draw = ImageDraw.Draw(preview_img)
                box_color = (int(60 + 100 * progress), int(100 + 80 * progress), int(200 + 40 * progress))
                draw.rectangle([8, 8, 56, 56], fill=box_color)
                buf = io.BytesIO()
                preview_img.save(buf, format="PNG")
                raw_b64 = base64.b64encode(buf.getvalue()).decode("ascii")
                preview_b64 = f"data:image/png;base64,{raw_b64}"
            except Exception:
                preview_b64 = None

        return {
            "active": True,
            "progress": round(progress, 4),
            "progress_percent": round(progress * 100.0, 1),
            "sampling_step": current_step,
            "sampling_steps": total_steps,
            "eta_relative": eta,
            "interrupted": False,
            "preview_image": preview_b64,
            "preview_available": preview_b64 is not None,
        }

    @contextmanager
    def acquire(self, timeout: float | None = None):
        req_timeout = timeout if timeout is not None else self.default_timeout
        wait_start = time.perf_counter()

        with self._lock:
            if self._queued_jobs >= self.max_capacity:
                self._total_rejected += 1
                raise ApiError(
                    "queue_full",
                    f"The AI generation queue is full ({self._queued_jobs} jobs queued). Please retry shortly.",
                    429,
                )
            self._queued_jobs += 1

        acquired = False
        try:
            acquired = self._semaphore.acquire(timeout=req_timeout)
            if not acquired:
                with self._lock:
                    self._total_rejected += 1
                raise ApiError(
                    "queue_timeout",
                    f"Request timed out waiting in the generation queue after {req_timeout}s.",
                    504,
                )
            wait_duration_ms = (time.perf_counter() - wait_start) * 1000.0
            with self._lock:
                self._queued_jobs -= 1
                self._active_jobs += 1
                self._active_job_start = time.perf_counter()
                remaining_queued = self._queued_jobs

            exec_start = time.perf_counter()
            job_stats = {
                "wait_ms": round(wait_duration_ms, 1),
                "remaining_queued": remaining_queued,
                "exec_start": exec_start,
                "exec_ms": 0.0,
            }
            try:
                yield job_stats
                exec_duration_ms = (time.perf_counter() - exec_start) * 1000.0
                job_stats["exec_ms"] = round(exec_duration_ms, 1)
                with self._lock:
                    self._total_completed += 1
                    self._total_wait_time_ms += wait_duration_ms
                    self._total_exec_time_ms += exec_duration_ms
            except Exception:
                with self._lock:
                    self._total_failed += 1
                raise
            finally:
                with self._lock:
                    self._active_jobs -= 1
                    if self._active_jobs <= 0:
                        self._active_jobs = 0
                        self._active_job_start = 0.0
                self._semaphore.release()
        finally:
            if not acquired:
                with self._lock:
                    self._queued_jobs = max(0, self._queued_jobs - 1)


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


# ตรวจชื่อ provider ว่าต้องเรียก Forge หรือใช้ตัวสร้างภาพทดสอบ
def is_forge_provider(config: dict[str, Any]) -> bool:
    return str(config["PROVIDER_NAME"]).casefold() in {"forge", "webui-forge", "stable-diffusion-webui-forge"}


# สร้างข้อมูล HTTP Basic Auth เมื่อ Forge กำหนดชื่อผู้ใช้ไว้
def forge_auth(config: dict[str, Any]):
    username = str(config.get("FORGE_USERNAME", ""))
    password = str(config.get("FORGE_PASSWORD", ""))
    return (username, password) if username else None


# เรียก Forge ด้วยเวลารอที่กำหนด และแปลงปัญหาเครือข่ายหรือ HTTP เป็นข้อผิดพลาด provider
def forge_request(config: dict[str, Any], method: str, endpoint: str, **kwargs) -> requests.Response:
    url = f"{str(config['FORGE_URL']).rstrip('/')}{endpoint}"
    try:
        response = requests.request(
            method,
            url,
            auth=forge_auth(config),
            timeout=(float(config["FORGE_CONNECT_TIMEOUT"]), float(config["FORGE_READ_TIMEOUT"])),
            **kwargs,
        )
    except requests.RequestException as exc:
        raise ProviderUnavailable(f"WebUI Forge is unavailable at {config['FORGE_URL']}.") from exc
    # แปลง HTTP error ของบริการปลายทางเป็นข้อผิดพลาดของงาน
    if not response.ok:
        try:
            detail = response.json().get("detail") or response.json().get("error") or response.text
        except (ValueError, AttributeError):
            detail = response.text
        raise ProviderError(f"WebUI Forge returned HTTP {response.status_code}: {str(detail)[:300]}")
    return response


# อ่านข้อมูลเมทาดาต้าจากไฟล์ .cm-info.json ของ Stability Matrix
def read_cm_info(file_path: Path) -> dict[str, Any]:
    for candidate in (
        file_path.with_name(f"{file_path.name}.cm-info.json"),
        file_path.with_name(f"{file_path.stem}.cm-info.json"),
    ):
        if candidate.exists() and candidate.is_file():
            try:
                return json.loads(candidate.read_text(encoding="utf-8"))
            except Exception:
                pass
    return {}


# ค้นหาไฟล์ภาพตัวอย่าง (Preview) ของโมเดลหรือ LoRA
def find_preview_file(name: str, directory: str | Path) -> Path | None:
    dir_path = Path(directory)
    if not dir_path.exists():
        return None
    stem = Path(name).stem
    extensions = (".preview.jpeg", ".preview.jpg", ".preview.png", ".jpeg", ".jpg", ".png")
    for ext in extensions:
        candidate = dir_path / f"{stem}{ext}"
        if candidate.exists() and candidate.is_file():
            return candidate
        candidate2 = dir_path / f"{name}{ext}"
        if candidate2.exists() and candidate2.is_file():
            return candidate2
    return None


# สแกนโมเดล Checkpoint ทั้งหมดที่มีในเครื่อง
def scan_installed_models(config: dict[str, Any]) -> list[dict[str, Any]]:
    models_dir = Path(config.get("MODELS_DIR", r"C:\.Work_MasTer\StabilityMatrix\Data\Models\StableDiffusion"))
    items: list[dict[str, Any]] = []
    if models_dir.exists():
        files = sorted(models_dir.glob("*.safetensors")) + sorted(models_dir.glob("*.ckpt"))
        for f in files:
            info = read_cm_info(f)
            has_preview = find_preview_file(f.stem, models_dir) is not None
            items.append({
                "name": f.stem,
                "filename": f.name,
                "title": info.get("ModelName") or f.stem,
                "base_model": info.get("BaseModel", "SDXL 1.0"),
                "size_mb": round(f.stat().st_size / (1024 * 1024), 1),
                "tags": info.get("Tags", []),
                "author": info.get("AuthorUsername", ""),
                "has_preview": has_preview,
                "preview_url": f"/v1/preview/model/{f.stem}" if has_preview else None,
            })
    return items


# สแกน LoRA ทั้งหมดที่มีในเครื่องพร้อมคำสั่ง Tag ใช้งาน
def scan_installed_loras(config: dict[str, Any]) -> list[dict[str, Any]]:
    loras_dir = Path(config.get("LORAS_DIR", r"C:\.Work_MasTer\StabilityMatrix\Data\Models\Lora"))
    items: list[dict[str, Any]] = []
    if loras_dir.exists():
        files = sorted(loras_dir.glob("*.safetensors")) + sorted(loras_dir.glob("*.ckpt"))
        for f in files:
            info = read_cm_info(f)
            has_preview = find_preview_file(f.stem, loras_dir) is not None
            items.append({
                "name": f.stem,
                "filename": f.name,
                "title": info.get("ModelName") or f.stem,
                "base_model": info.get("BaseModel", "SDXL 1.0"),
                "size_mb": round(f.stat().st_size / (1024 * 1024), 1),
                "trained_words": info.get("TrainedWords", []),
                "tags": info.get("Tags", []),
                "author": info.get("AuthorUsername", ""),
                "tag": f"<lora:{f.stem}:1.0>",
                "has_preview": has_preview,
                "preview_url": f"/v1/preview/lora/{f.stem}" if has_preview else None,
            })
    return items


# ดึงสถานะ Live Progress จาก WebUI Forge หรือระบบจำลองตาม Provider ที่กำลังทำงาน
def get_live_progress(
    config: dict[str, Any],
    queue_manager: GenerationQueueManager,
    include_preview: bool = False,
) -> dict[str, Any]:
    queue_info = {
        "gpu_available": queue_manager.active_jobs < queue_manager.max_concurrency,
        "active_jobs": queue_manager.active_jobs,
        "queued_jobs": queue_manager.queued_jobs,
        "max_concurrency": queue_manager.max_concurrency,
    }

    if is_forge_provider(config):
        query_param = "false" if include_preview else "true"
        try:
            resp = forge_request(config, "GET", f"/sdapi/v1/progress?skip_current_image={query_param}")
            data = resp.json()
            progress = round(float(data.get("progress", 0.0)), 4)
            eta = round(float(data.get("eta_relative", 0.0)), 1)
            state = data.get("state") or {}
            step = int(state.get("sampling_step", 0))
            steps = int(state.get("sampling_steps", 0))
            interrupted = bool(state.get("interrupted", False))
            current_img = data.get("current_image")

            preview_b64 = None
            if include_preview and current_img:
                current_img_str = str(current_img).strip()
                if current_img_str.startswith("data:image"):
                    preview_b64 = current_img_str
                else:
                    preview_b64 = f"data:image/png;base64,{current_img_str}"

            is_active = progress > 0.0 or step > 0 or queue_manager.active_jobs > 0

            return {
                "status": "ok",
                "active": is_active,
                "progress": progress,
                "progress_percent": round(progress * 100.0, 1),
                "sampling_step": step,
                "sampling_steps": steps,
                "eta_relative": eta,
                "interrupted": interrupted,
                "preview_image": preview_b64,
                "preview_available": preview_b64 is not None,
                "provider": "forge",
                "queue": queue_info,
            }
        except Exception:
            sim = queue_manager.live_progress_simulation(
                default_steps=int(config.get("FORGE_DEFAULT_STEPS", 20)),
                include_preview=include_preview,
            )
            sim.update({
                "status": "ok",
                "provider": "forge",
                "forge_connected": False,
                "queue": queue_info,
            })
            return sim

    # Development-procedural provider simulation
    sim = queue_manager.live_progress_simulation(
        default_steps=20,
        include_preview=include_preview,
    )
    sim.update({
        "status": "ok",
        "provider": "development-procedural",
        "queue": queue_info,
    })
    return sim


# รายการ Sampler มาตรฐานพร้อมคำอธิบายและจำนวน steps แนะนำ
DEFAULT_SAMPLERS: list[dict[str, Any]] = [
    {
        "name": "Euler a",
        "label": "Euler Ancestral (Euler a)",
        "category": "Ancestral",
        "description": "Fast and creative with soft blending. Excellent for anime illustrations.",
        "recommended_steps": [20, 30],
    },
    {
        "name": "Euler",
        "label": "Euler",
        "category": "Standard",
        "description": "Deterministic, smooth, and fast. Great baseline for all models.",
        "recommended_steps": [18, 25],
    },
    {
        "name": "DPM++ 2M Karras",
        "label": "DPM++ 2M Karras",
        "category": "DPM-Solver",
        "description": "High detail, crisp lines, and clean geometry. Industry standard for SDXL / Illustrious.",
        "recommended_steps": [20, 35],
    },
    {
        "name": "DPM++ 2M SDE Karras",
        "label": "DPM++ 2M SDE Karras",
        "category": "DPM-Solver (SDE)",
        "description": "Adds subtle stochastic variation for richer texture, hair, and lighting.",
        "recommended_steps": [24, 35],
    },
    {
        "name": "DPM++ SDE Karras",
        "label": "DPM++ SDE Karras",
        "category": "DPM-Solver (SDE)",
        "description": "Ultra fine details, micro textures, and depth at slightly higher step counts.",
        "recommended_steps": [25, 40],
    },
    {
        "name": "DPM++ 2S a Karras",
        "label": "DPM++ 2S a Karras",
        "category": "Ancestral",
        "description": "Second-order ancestral solver for dynamic, painterly output.",
        "recommended_steps": [20, 35],
    },
    {
        "name": "DDIM",
        "label": "DDIM",
        "category": "Deterministic",
        "description": "Classic deterministic sampler with predictable latent trajectory.",
        "recommended_steps": [20, 40],
    },
    {
        "name": "UniPC",
        "label": "UniPC",
        "category": "Fast Predictor-Corrector",
        "description": "Fast convergence sampler capable of decent quality at lower step counts.",
        "recommended_steps": [15, 25],
    },
    {
        "name": "LCM",
        "label": "LCM (Latent Consistency Model)",
        "category": "Ultra Fast",
        "description": "Ultra-fast generation for rapid prototyping at 4 to 10 steps.",
        "recommended_steps": [4, 10],
    },
]

# รายการ Scheduler สำหรับควบคุม Noise Schedule
DEFAULT_SCHEDULERS: list[dict[str, Any]] = [
    {
        "name": "Automatic",
        "label": "Automatic (WebUI Default)",
        "description": "Automatically selects the optimal schedule for the chosen sampler.",
    },
    {
        "name": "Karras",
        "label": "Karras",
        "description": "Noise schedule optimized by Karras et al. Recommended for DPM++ samplers.",
    },
    {
        "name": "Exponential",
        "label": "Exponential",
        "description": "Exponential noise curve, good for high-contrast illustrations.",
    },
    {
        "name": "SGM Uniform",
        "label": "SGM Uniform",
        "description": "Uniform schedule common in SDXL base pipelines.",
    },
    {
        "name": "Simple",
        "label": "Simple",
        "description": "Linear variance schedule with balanced details.",
    },
    {
        "name": "Normal",
        "label": "Normal",
        "description": "Standard schedule from original Stable Diffusion.",
    },
    {
        "name": "DDIM Uniform",
        "label": "DDIM Uniform",
        "description": "Uniform schedule specifically designed for DDIM sampling.",
    },
    {
        "name": "Beta",
        "label": "Beta",
        "description": "Beta distribution schedule for smooth gradients.",
    },
]

# ชุด Presets สำเร็จรูปสำหรับสไตล์และคุณภาพภาพที่นิยม
QUALITY_PRESETS: list[dict[str, Any]] = [
    {
        "id": "anime_masterpiece",
        "name": "Anime Masterpiece",
        "description": "Optimized for anime character portraits, smooth cell shading, and clean linework (Illustrious / Animagine).",
        "sampler": "DPM++ 2M Karras",
        "scheduler": "Karras",
        "steps": 28,
        "cfg_scale": 7.0,
        "clip_skip": 2,
    },
    {
        "id": "creative_vibrant",
        "name": "Creative & Dynamic",
        "description": "Encourages diverse poses, vibrant color saturation, and expressive backgrounds.",
        "sampler": "Euler a",
        "scheduler": "Simple",
        "steps": 25,
        "cfg_scale": 7.5,
        "clip_skip": 2,
    },
    {
        "id": "sharp_details",
        "name": "Crisp & High-Detail",
        "description": "Maximum texture clarity, intricate costume details, and fine environmental lighting.",
        "sampler": "DPM++ 2M SDE Karras",
        "scheduler": "Karras",
        "steps": 32,
        "cfg_scale": 6.5,
        "clip_skip": 2,
    },
    {
        "id": "fast_draft",
        "name": "Fast Preview Draft",
        "description": "Rapid generation for testing prompts, poses, or LoRA combinations in minimal time.",
        "sampler": "Euler",
        "scheduler": "Normal",
        "steps": 16,
        "cfg_scale": 6.0,
        "clip_skip": 2,
    },
]

# อัตราส่วนและขนาดภาพมาตรฐานสำหรับ SDXL และ SD 1.5
ASPECT_RATIOS: list[dict[str, Any]] = [
    {"label": "1:1 Square (1024x1024)", "width": 1024, "height": 1024, "aspect_ratio": "1:1", "recommended_for": "Avatars & Icons"},
    {"label": "2:3 Portrait (832x1216)", "width": 832, "height": 1216, "aspect_ratio": "2:3", "recommended_for": "Full Body & Anime Character Art"},
    {"label": "3:2 Landscape (1216x832)", "width": 1216, "height": 832, "aspect_ratio": "3:2", "recommended_for": "Scenery & Wallpapers"},
    {"label": "3:4 Portrait (768x1024)", "width": 768, "height": 1024, "aspect_ratio": "3:4", "recommended_for": "Waist-up Character Portrait"},
    {"label": "4:3 Landscape (1024x768)", "width": 1024, "height": 768, "aspect_ratio": "4:3", "recommended_for": "Standard Horizontal Art"},
    {"label": "1:1 Medium Square (768x768)", "width": 768, "height": 768, "aspect_ratio": "1:1", "recommended_for": "Fast Square Generation"},
    {"label": "1:1 Classic Square (512x512)", "width": 512, "height": 512, "aspect_ratio": "1:1", "recommended_for": "SD 1.5 Legacy"},
]

# คอลเลกชัน Style Presets พร้อมคำอธิบาย ตัวปรับแต่ง Prompt และพารามิเตอร์ที่เหมาะสม
STYLE_PRESETS: list[dict[str, Any]] = [
    {
        "id": "anime_illustrious",
        "name": "Anime Masterpiece",
        "category": "Anime & Manga",
        "description": "Top-tier modern anime style with clean cel-shading, expressive eyes, vibrant colors, and sharp linework (Illustrious / Animagine / SDXL).",
        "prompt_prefix": "masterpiece, best quality, ultra-detailed anime illustration,",
        "prompt_suffix": "vibrant colors, clean sharp lineart, anime aesthetic, dynamic composition, 8k resolution",
        "negative_prompt": "photorealistic, real photo, 3d render, deformed, bad anatomy, bad hands, missing fingers, extra limbs, low quality, blurry, watermark",
        "recommended_sampler": "DPM++ 2M Karras",
        "recommended_scheduler": "Karras",
        "cfg_scale": 7.0,
        "recommended_steps": 28,
        "clip_skip": 2,
    },
    {
        "id": "cyberpunk_neon",
        "name": "Cyberpunk & Sci-Fi Neon",
        "category": "Sci-Fi & Futuristic",
        "description": "Futuristic dystopian cityscapes, neon reflections, glowing holograms, and high-tech cybernetics.",
        "prompt_prefix": "cyberpunk aesthetic, high-tech dystopian city, neon glow,",
        "prompt_suffix": "volumetric lighting, holographic displays, chromatic aberration, ray tracing, octane render, photorealistic sci-fi, 8k",
        "negative_prompt": "vintage, rustic, medieval, low resolution, washed out, blurry, cartoon, flat colors",
        "recommended_sampler": "Euler a",
        "recommended_scheduler": "Simple",
        "cfg_scale": 7.5,
        "recommended_steps": 26,
        "clip_skip": 2,
    },
    {
        "id": "photorealistic_cinematic",
        "name": "Cinematic Film Photography",
        "category": "Photorealistic",
        "description": "True-to-life 35mm film photography with shallow depth of field, natural lighting, and authentic skin texture.",
        "prompt_prefix": "raw cinematic photo, 35mm film photography, award winning portrait,",
        "prompt_suffix": "natural skin texture, subsurface scattering, bokeh, golden hour lighting, shot on ARRI Alexa, photorealistic, 8k uhd",
        "negative_prompt": "anime, cartoon, graphic, drawing, painting, illustration, 3d render, plastic smooth skin, oversaturated, deformed, watermark",
        "recommended_sampler": "DPM++ 2M SDE Karras",
        "recommended_scheduler": "Karras",
        "cfg_scale": 6.0,
        "recommended_steps": 32,
        "clip_skip": 1,
    },
    {
        "id": "fantasy_oil_painting",
        "name": "Fantasy Classical Oil Painting",
        "category": "Artistic & Traditional",
        "description": "Rich, painterly oil on canvas with expressive brushstrokes, chiaroscuro lighting, and mythic grandeur.",
        "prompt_prefix": "epic fantasy oil painting, classical masterpiece style,",
        "prompt_suffix": "visible brush strokes, dramatic chiaroscuro lighting, rich oil canvas texture, trending on ArtStation, museum quality",
        "negative_prompt": "photograph, modern, 3d render, flat digital art, low contrast, oversaturated, vector",
        "recommended_sampler": "DPM++ 2S a Karras",
        "recommended_scheduler": "Karras",
        "cfg_scale": 7.5,
        "recommended_steps": 30,
        "clip_skip": 2,
    },
    {
        "id": "studio_ghibli",
        "name": "Studio Ghibli Nostalgia",
        "category": "Anime & Manga",
        "description": "Heartwarming hand-painted anime aesthetic inspired by Hayao Miyazaki, lush nature, and whimsical blue skies.",
        "prompt_prefix": "studio ghibli aesthetic, anime scenery, hayao miyazaki style,",
        "prompt_suffix": "hand-painted watercolor background, lush greenery, nostalgic afternoon atmosphere, whimsical, soft pastel colors, clouds",
        "negative_prompt": "dark, moody, photorealistic, 3d, neon, gritty, high contrast, harsh shadows, horror",
        "recommended_sampler": "Euler a",
        "recommended_scheduler": "Simple",
        "cfg_scale": 7.0,
        "recommended_steps": 24,
        "clip_skip": 2,
    },
    {
        "id": "dark_fantasy",
        "name": "Dark Fantasy & Gothic",
        "category": "Artistic & Traditional",
        "description": "Grimdark atmosphere with eldritch ruins, ornate gothic armor, atmospheric fog, and dramatic rim lighting.",
        "prompt_prefix": "dark fantasy aesthetic, grimdark gothic atmosphere, eldritch,",
        "prompt_suffix": "fog and embers, dramatic rim light, intricate gothic armor, moody color grading, detailed dark art, 8k",
        "negative_prompt": "bright, cheerful, cute, anime, pastel, low detail, flat lighting, sunny",
        "recommended_sampler": "DPM++ 2M Karras",
        "recommended_scheduler": "Exponential",
        "cfg_scale": 7.0,
        "recommended_steps": 30,
        "clip_skip": 2,
    },
    {
        "id": "pixel_art",
        "name": "Retro 16-Bit Pixel Art",
        "category": "Digital Art & Retro",
        "description": "Charming nostalgic 16-bit arcade and SNES era pixel graphics with dithering and hand-placed sprites.",
        "prompt_prefix": "pixel art masterpiece, 16-bit retro game visual,",
        "prompt_suffix": "isometric view, pixelated dithering, nostalgic arcade game aesthetic, vibrant limited palette, crisp pixel edges",
        "negative_prompt": "smooth gradient, high-res photo, 3d render, blurry, vector art, realistic",
        "recommended_sampler": "Euler",
        "recommended_scheduler": "Normal",
        "cfg_scale": 7.0,
        "recommended_steps": 20,
        "clip_skip": 1,
    },
    {
        "id": "vaporwave_synthwave",
        "name": "Synthwave & Vaporwave 80s",
        "category": "Sci-Fi & Futuristic",
        "description": "Retro 80s synthwave neon grid, glowing cyan and magenta wireframes, palm trees, and VHS nostalgia.",
        "prompt_prefix": "synthwave retro 80s aesthetic, vaporwave neon dream,",
        "prompt_suffix": "purple and cyan sunset, wireframe grid, VHS tape glitch artifact, retrofuturistic, nostalgic, outrun",
        "negative_prompt": "modern photo, natural landscape, monochrome, dull, low quality, washed out",
        "recommended_sampler": "Euler a",
        "recommended_scheduler": "Simple",
        "cfg_scale": 7.5,
        "recommended_steps": 25,
        "clip_skip": 2,
    },
    {
        "id": "manga_lineart",
        "name": "Japanese Manga Ink & Screentone",
        "category": "Anime & Manga",
        "description": "High-contrast monochrome Japanese comic art with screentone shading, dynamic hatching, and bold ink lines.",
        "prompt_prefix": "clean black and white manga illustration, authentic Japanese comic style,",
        "prompt_suffix": "screentone shading, dynamic ink linework, cross-hatching, high contrast monochrome, shonen jump cover art",
        "negative_prompt": "color, colored, watercolor, photorealistic, 3d, gradient, blurry",
        "recommended_sampler": "Euler",
        "recommended_scheduler": "Normal",
        "cfg_scale": 8.0,
        "recommended_steps": 22,
        "clip_skip": 2,
    },
    {
        "id": "watercolor_splatter",
        "name": "Watercolor & Fluid Ink",
        "category": "Artistic & Traditional",
        "description": "Expressive fluid watercolor pigments on cold-press textured paper with organic water blooms and delicate edges.",
        "prompt_prefix": "delicate watercolor painting, flowing ink wash and pigments,",
        "prompt_suffix": "paper texture, organic color bleeds, translucent layers, soft edges, ethereal fine art, artistic splatters",
        "negative_prompt": "solid digital lines, 3d render, sharp geometric edges, photorealistic, harsh contrast",
        "recommended_sampler": "Euler a",
        "recommended_scheduler": "Simple",
        "cfg_scale": 6.5,
        "recommended_steps": 25,
        "clip_skip": 2,
    },
]

# ดึงข้อมูล Style Preset ตาม id หรือค้นหาจากชื่อ
def get_style_preset_by_id(identifier: str | None) -> dict[str, Any] | None:
    if not identifier:
        return None
    key = identifier.strip().casefold()
    for preset in STYLE_PRESETS:
        if preset["id"].casefold() == key or preset["name"].casefold() == key:
            return preset
        if key in preset["id"].casefold():
            return preset
    return None

# ปรับแต่ง Prompt และพารามิเตอร์ตาม Style Preset ที่เลือก
def apply_style_preset(
    preset_id: str | None,
    prompt: str,
    negative_prompt: str = "",
    sampler: str | None = None,
    scheduler: str | None = None,
    cfg_scale: float | None = None,
    clip_skip: int | None = None,
    steps: int | None = None,
) -> tuple[str, str, str | None, str | None, float | None, int | None, int | None, dict[str, Any] | None]:
    preset = get_style_preset_by_id(preset_id)
    if not preset:
        return prompt, negative_prompt, sampler, scheduler, cfg_scale, clip_skip, steps, None

    enhanced_prompt = prompt
    prefix = preset.get("prompt_prefix", "")
    suffix = preset.get("prompt_suffix", "")
    if prefix and prefix.casefold() not in prompt.casefold():
        enhanced_prompt = f"{prefix} {enhanced_prompt}"
    if suffix and suffix.casefold() not in prompt.casefold():
        enhanced_prompt = f"{enhanced_prompt}, {suffix}"

    preset_neg = preset.get("negative_prompt", "")
    if preset_neg:
        if negative_prompt and negative_prompt.strip():
            enhanced_neg = f"{negative_prompt.strip()}, {preset_neg}"
        else:
            enhanced_neg = preset_neg
    else:
        enhanced_neg = negative_prompt

    eff_sampler = sampler or preset.get("recommended_sampler")
    eff_scheduler = scheduler or preset.get("recommended_scheduler")
    eff_cfg = cfg_scale if cfg_scale is not None else preset.get("cfg_scale")
    eff_clip = clip_skip if clip_skip is not None else preset.get("clip_skip")
    eff_steps = steps if (steps is not None and steps != 20) else (preset.get("recommended_steps") or steps or 20)

    return enhanced_prompt, enhanced_neg, eff_sampler, eff_scheduler, eff_cfg, eff_clip, eff_steps, preset



# ดึงรายชื่อ Sampler จาก Forge ถ้าเปิดอยู่ หรือส่งคืนรายการมาตรฐานที่เตรียมไว้
def get_supported_samplers(config: dict[str, Any]) -> list[dict[str, Any]]:
    if is_forge_provider(config):
        try:
            resp = forge_request(config, "GET", "/sdapi/v1/samplers")
            data = resp.json()
            if isinstance(data, list) and data:
                return [
                    {
                        "name": item.get("name", ""),
                        "label": item.get("name", ""),
                        "aliases": item.get("aliases", []),
                        "options": item.get("options", {}),
                    }
                    for item in data
                    if item.get("name")
                ]
        except Exception:
            pass
    return DEFAULT_SAMPLERS


# ดึงรายชื่อ Scheduler จาก Forge ถ้าเปิดอยู่ หรือส่งคืนรายการมาตรฐานที่เตรียมไว้
def get_supported_schedulers(config: dict[str, Any]) -> list[dict[str, Any]]:
    if is_forge_provider(config):
        try:
            resp = forge_request(config, "GET", "/sdapi/v1/schedulers")
            data = resp.json()
            if isinstance(data, list) and data:
                return [
                    {
                        "name": item.get("name") or item.get("label", ""),
                        "label": item.get("label") or item.get("name", ""),
                    }
                    for item in data
                    if item.get("name") or item.get("label")
                ]
        except Exception:
            pass
    return DEFAULT_SCHEDULERS


# ประกอบพารามิเตอร์ร่วมของ Forge พร้อม sampler, scheduler, checkpoint, LoRA และ clip_skip
def forge_payload(
    config: dict[str, Any],
    prompt: str,
    seed: int,
    steps: int,
    model: str | None = None,
    loras: list[Any] | None = None,
    sampler: str | None = None,
    scheduler: str | None = None,
    cfg_scale: float | None = None,
    clip_skip: int | None = None,
) -> dict[str, Any]:
    final_prompt = prompt
    if loras:
        for item in loras:
            if isinstance(item, str) and item.strip():
                tag = f"<lora:{item.strip()}:1.0>"
                if tag not in final_prompt:
                    final_prompt = f"{final_prompt} {tag}"
            elif isinstance(item, dict):
                name = str(item.get("name", "")).strip()
                weight = float(item.get("weight", 1.0))
                if name:
                    tag = f"<lora:{name}:{weight}>"
                    if tag not in final_prompt:
                        final_prompt = f"{final_prompt} {tag}"

    cfg = float(cfg_scale) if cfg_scale is not None else float(config["FORGE_CFG_SCALE"])
    sampler_name = sampler or config["FORGE_SAMPLER"]

    payload: dict[str, Any] = {
        "prompt": final_prompt,
        "seed": seed,
        "steps": steps,
        "cfg_scale": cfg,
        "sampler_name": sampler_name,
        "batch_size": 1,
        "n_iter": 1,
        "send_images": True,
        "save_images": False,
    }
    active_scheduler = scheduler or config.get("FORGE_SCHEDULER")
    if active_scheduler and active_scheduler.strip() and active_scheduler.lower() != "automatic":
        payload["scheduler"] = active_scheduler

    override_settings: dict[str, Any] = {}
    active_checkpoint = model or config.get("FORGE_CHECKPOINT")
    if active_checkpoint:
        override_settings["sd_model_checkpoint"] = active_checkpoint
    if clip_skip is not None:
        override_settings["CLIP_stop_at_last_layers"] = int(clip_skip)

    if override_settings:
        payload["override_settings"] = override_settings
        payload["override_settings_restore_afterwards"] = True
    return payload


# ถอด Base64 เปิดภาพ และอ่าน seed ที่ Forge รายงานกลับ
def decode_forge_image(response: requests.Response, fallback_seed: int) -> tuple[Image.Image, int]:
    try:
        data = response.json()
        encoded = data["images"][0]
        if "," in encoded:
            encoded = encoded.split(",", 1)[1]
        # แปลงข้อความ Base64 เป็นไบต์ภาพ ไม่ใช่การถอดรหัสลับ
        raw_image = base64.b64decode(encoded)
        image = Image.open(io.BytesIO(raw_image))
        image.load()
        returned_seed = fallback_seed
        info = data.get("info")
        if isinstance(info, str) and info:
            parsed_info = json.loads(info)
            returned_seed = int(parsed_info.get("seed", fallback_seed))
        return image.convert("RGB"), returned_seed
    except (KeyError, IndexError, TypeError, ValueError, json.JSONDecodeError, UnidentifiedImageError) as exc:
        raise ProviderError("WebUI Forge returned an invalid image response.") from exc


# ส่งข้อความและขนาดภาพไปยัง txt2img แล้วถอดภาพผลลัพธ์
def generate_forge_image(
    config: dict[str, Any],
    prompt: str,
    negative_prompt: str,
    width: int,
    height: int,
    seed: int,
    steps: int,
    model: str | None = None,
    loras: list[Any] | None = None,
    sampler: str | None = None,
    scheduler: str | None = None,
    cfg_scale: float | None = None,
    clip_skip: int | None = None,
) -> tuple[Image.Image, int]:
    payload = forge_payload(
        config,
        prompt,
        seed,
        steps,
        model=model,
        loras=loras,
        sampler=sampler,
        scheduler=scheduler,
        cfg_scale=cfg_scale,
        clip_skip=clip_skip,
    )
    payload.update({"negative_prompt": negative_prompt, "width": width, "height": height})
    response = forge_request(config, "POST", "/sdapi/v1/txt2img", json=payload)
    return decode_forge_image(response, seed)


# ปรับแนวและขนาดภาพ เข้ารหัสต้นทาง แล้วเรียก img2img ด้วย denoising_strength
def edit_forge_image(
    config: dict[str, Any],
    source: Image.Image,
    prompt: str,
    strength: float,
    seed: int,
    model: str | None = None,
    loras: list[Any] | None = None,
    sampler: str | None = None,
    scheduler: str | None = None,
    cfg_scale: float | None = None,
    clip_skip: int | None = None,
) -> tuple[Image.Image, int]:
    image = ImageOps.exif_transpose(source).convert("RGB")
    # ย่อภาพให้อยู่ในขอบเขตขนาดที่กำหนดโดยคงอัตราส่วน
    image.thumbnail((MAX_DIMENSION, MAX_DIMENSION), Image.Resampling.LANCZOS)
    source_buffer = io.BytesIO()
    image.save(source_buffer, format="PNG")
    payload = forge_payload(
        config,
        prompt,
        seed,
        int(config["FORGE_EDIT_STEPS"]),
        model=model,
        loras=loras,
        sampler=sampler,
        scheduler=scheduler,
        cfg_scale=cfg_scale,
        clip_skip=clip_skip,
    )
    payload.update(
        {
            "negative_prompt": "",
            "init_images": [base64.b64encode(source_buffer.getvalue()).decode("ascii")],
            "denoising_strength": strength,
            "resize_mode": 0,
            "width": image.width,
            "height": image.height,
        }
    )
    response = forge_request(config, "POST", "/sdapi/v1/img2img", json=payload)
    return decode_forge_image(response, seed)



# สร้างชุดสีจากตัวสุ่มที่กำหนด seed สำหรับภาพทดสอบ
def _palette(rng: random.Random) -> list[tuple[int, int, int]]:
    base = rng.randrange(360)

    # แปลงสี HLS เป็น RGB ในช่วง 0 ถึง 255 สำหรับวาดภาพ
    def hsl(hue: float, saturation: float, lightness: float) -> tuple[int, int, int]:
        import colorsys

        red, green, blue = colorsys.hls_to_rgb((hue % 360) / 360, lightness, saturation)
        return int(red * 255), int(green * 255), int(blue * 255)

    return [hsl(base, 0.64, 0.13), hsl(base + 48, 0.72, 0.42), hsl(base + 168, 0.58, 0.55), hsl(base + 290, 0.68, 0.63)]


# วาดภาพตัวอย่างด้วย Pillow จาก seed และ prompt โดยไม่ใช้โมเดลที่ผ่านการฝึก
def generate_development_image(
    prompt: str,
    width: int,
    height: int,
    seed: int,
    model: str | None = None,
    loras: list[Any] | None = None,
    sampler: str | None = None,
    scheduler: str | None = None,
    cfg_scale: float | None = None,
    clip_skip: int | None = None,
    style_preset: str | None = None,
) -> Image.Image:
    rng = random.Random(seed)
    palette = _palette(rng)
    image = Image.new("RGB", (width, height), palette[0])
    draw = ImageDraw.Draw(image, "RGBA")

    # วาดพื้นหลังไล่สีทีละแถวสำหรับ provider ทดสอบ

    for y in range(height):
        ratio = y / max(height - 1, 1)
        start, end = palette[0], palette[1]
        color = tuple(int(start[channel] * (1 - ratio) + end[channel] * ratio) for channel in range(3))
        draw.line((0, y, width, y), fill=(*color, 255))

    # วาดวงสีโปร่งใสด้วยตัวสุ่มที่ควบคุม seed

    for _ in range(28):
        radius = rng.randint(max(18, width // 16), max(40, width // 3))
        x = rng.randint(-radius, width + radius)
        y = rng.randint(-radius, height + radius)
        color = rng.choice(palette[1:])
        alpha = rng.randint(30, 125)
        draw.ellipse((x - radius, y - radius, x + radius, y + radius), fill=(*color, alpha))

    # เพิ่มรูปหลายเหลี่ยมเพื่อสร้างลวดลายของภาพทดสอบ

    for _ in range(10):
        points = [(rng.randint(0, width), rng.randint(0, height)) for _ in range(rng.randint(3, 7))]
        color = rng.choice(palette)
        draw.polygon(points, fill=(*color, rng.randint(18, 55)))

    image = image.filter(ImageFilter.GaussianBlur(radius=max(2, width // 170)))
    # วาดแผ่นข้อความ prompt และป้ายระบุว่าเป็นภาพจาก provider ทดสอบ
    overlay = Image.new("RGBA", image.size, (0, 0, 0, 0))
    overlay_draw = ImageDraw.Draw(overlay)
    margin = max(20, width // 22)
    box_height = min(height // 4, 150)
    overlay_draw.rounded_rectangle(
        (margin, height - box_height - margin, width - margin, height - margin),
        radius=max(12, width // 40),
        fill=(6, 7, 15, 155),
        outline=(255, 255, 255, 35),
        width=1,
    )
    font = ImageFont.load_default(size=max(12, min(22, width // 28)))
    wrapped = "\n".join(textwrap.wrap(prompt, width=max(24, width // 15))[:3])
    overlay_draw.multiline_text((margin * 1.6, height - box_height), wrapped, font=font, fill=(245, 245, 250, 235), spacing=6)
    badge = f"LUMA DEV  /  SEED {seed}"
    if model:
        badge += f"  /  {model}"
    if style_preset:
        badge += f"  /  {style_preset.upper()}"
    overlay_draw.text((margin * 1.6, height - margin * 1.7), badge, font=ImageFont.load_default(), fill=(190, 180, 230, 210))
    return Image.alpha_composite(image.convert("RGBA"), overlay).convert("RGB")


# เลือกเอฟเฟกต์พื้นฐานตามคำใน prompt แล้วผสมภาพตาม strength สำหรับทดสอบ
def edit_development_image(
    source: Image.Image,
    prompt: str,
    strength: float,
    seed: int,
    model: str | None = None,
    loras: list[Any] | None = None,
    sampler: str | None = None,
    scheduler: str | None = None,
    cfg_scale: float | None = None,
    clip_skip: int | None = None,
    style_preset: str | None = None,
) -> Image.Image:

    image = ImageOps.exif_transpose(source).convert("RGB")
    image.thumbnail((MAX_DIMENSION, MAX_DIMENSION), Image.Resampling.LANCZOS)
    rng = random.Random(seed)
    words = prompt.casefold()

    # เลือกเอฟเฟกต์ตามคำภาษาอังกฤษใน prompt ของโหมดทดสอบ

    if "grayscale" in words or "black and white" in words or "monochrome" in words:
        transformed = ImageOps.grayscale(image).convert("RGB")
    elif "vintage" in words or "sepia" in words:
        gray = ImageOps.grayscale(image)
        transformed = ImageOps.colorize(gray, "#281811", "#efc98f")
    else:
        transformed = ImageEnhance.Color(image).enhance(1.0 + strength * 0.9)
        transformed = ImageEnhance.Contrast(transformed).enhance(1.0 + strength * 0.35)

    if "blur" in words or "dream" in words or "soft" in words:
        transformed = transformed.filter(ImageFilter.GaussianBlur(radius=1 + strength * 4))
    if "poster" in words or "comic" in words:
        transformed = ImageOps.posterize(transformed, max(3, 7 - round(strength * 4)))

    # ผสมสี พื้นผิว และภาพต้นทางตามค่า strength

    tint = Image.new("RGB", transformed.size, _palette(rng)[2])
    tinted = Image.blend(transformed, tint, strength * 0.18)
    texture = Image.effect_noise(transformed.size, 10 + strength * 22).convert("RGB")
    textured = ImageChops.soft_light(tinted, texture)
    return Image.blend(image, textured, strength)


# ดึงข้อความจากข้อผิดพลาดตรวจข้อมูลของ FastAPI ให้ใช้รูปแบบเดียวกับ API
def validation_message(error: RequestValidationError) -> str:
    if not error.errors():
        return "The request is invalid."
    detail = error.errors()[0]
    context_error = detail.get("ctx", {}).get("error")
    message = str(context_error or detail.get("msg") or "The request is invalid.")
    return message.removeprefix("Value error, ")


# สร้างแอปจากค่ากำหนด เชื่อมบริการ และลงทะเบียนเส้นทางกับตัวจัดการข้อผิดพลาด
def create_app(test_config: dict[str, Any] | None = None) -> FastAPI:
    config: dict[str, Any] = {
        "MAX_CONTENT_LENGTH": int(os.getenv("MAX_CONTENT_LENGTH", str(16 * 1024 * 1024))),
        "SERVICE_TOKEN": os.getenv("AI_SERVICE_TOKEN", "change-me-in-production"),
        "PROVIDER_NAME": os.getenv("AI_PROVIDER", "development-procedural"),
        "FORGE_URL": os.getenv("FORGE_URL", "http://127.0.0.1:7860"),
        "FORGE_USERNAME": os.getenv("FORGE_USERNAME", ""),
        "FORGE_PASSWORD": os.getenv("FORGE_PASSWORD", ""),
        "FORGE_CHECKPOINT": os.getenv("FORGE_CHECKPOINT", ""),
        "FORGE_SAMPLER": os.getenv("FORGE_SAMPLER", "Euler"),
        "FORGE_SCHEDULER": os.getenv("FORGE_SCHEDULER", ""),
        "FORGE_CFG_SCALE": float(os.getenv("FORGE_CFG_SCALE", "7")),
        "FORGE_EDIT_STEPS": int(os.getenv("FORGE_EDIT_STEPS", "20")),
        "FORGE_CONNECT_TIMEOUT": float(os.getenv("FORGE_CONNECT_TIMEOUT", "5")),
        "FORGE_READ_TIMEOUT": float(os.getenv("FORGE_READ_TIMEOUT", "300")),
        "MODELS_DIR": os.getenv("MODELS_DIR", r"C:\.Work_MasTer\StabilityMatrix\Data\Models\StableDiffusion"),
        "LORAS_DIR": os.getenv("LORAS_DIR", r"C:\.Work_MasTer\StabilityMatrix\Data\Models\Lora"),
        "CLIP_SKIP": int(os.getenv("CLIP_SKIP", "2")),
        "MAX_CONCURRENT_GENERATIONS": int(os.getenv("MAX_CONCURRENT_GENERATIONS", "1")),
        "MAX_QUEUE_CAPACITY": int(os.getenv("MAX_QUEUE_CAPACITY", "20")),
        "QUEUE_TIMEOUT_SECONDS": float(os.getenv("QUEUE_TIMEOUT_SECONDS", "180.0")),
    }
    if test_config:
        config.update(test_config)

    # ตัวจัดการคิวและความพร้อมกันของ GPU ประจำแอป
    queue_manager = GenerationQueueManager(
        max_concurrency=int(config["MAX_CONCURRENT_GENERATIONS"]),
        max_capacity=int(config["MAX_QUEUE_CAPACITY"]),
        default_timeout=float(config["QUEUE_TIMEOUT_SECONDS"]),
    )

    # ตั้งรูปแบบบันทึกเพื่อใช้วิเคราะห์การทำงานของบริการ

    logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"))
    app = FastAPI(
        title="LUMA AI Service",
        description="Private authenticated wrapper for WebUI Forge image generation and editing.",
        version="1.0.0",
    )
    # เก็บค่ากำหนดและตัวจัดการคิวไว้กับแอปเพื่อให้ endpoint ใช้ร่วมกัน
    app.state.config = config
    app.state.queue = queue_manager
    app.state.queue_manager = queue_manager

    # แปลง ApiError เป็นคำตอบ JSON ตามรหัสที่บริการกำหนด
    @app.exception_handler(ApiError)
    async def api_error_handler(_request: Request, error: ApiError):
        return error_response(error.code, error.message, error.status_code)

    # แปลงข้อผิดพลาดของ Pydantic เป็น HTTP 400 ตามสัญญา LUMA
    @app.exception_handler(RequestValidationError)
    async def validation_error_handler(_request: Request, error: RequestValidationError):
        return error_response("validation_error", validation_message(error), 400)

    # แปลงข้อผิดพลาด HTTP ของเฟรมเวิร์กให้เป็นรูปแบบ JSON ของระบบ
    @app.exception_handler(StarletteHTTPException)
    async def http_error_handler(_request: Request, error: StarletteHTTPException):
        if error.status_code == 404:
            return error_response("not_found", "The requested endpoint does not exist.", 404)
        return error_response("http_error", str(error.detail), error.status_code)

    # ตรวจ Content-Length ก่อนประมวลผลคำขอ ส่วนไฟล์อัปโหลดมีการตรวจขนาดอีกครั้ง
    @app.middleware("http")
    async def limit_request_size(request: Request, call_next):
        content_length = request.headers.get("content-length")
        if content_length:
            try:
                if int(content_length) > int(config["MAX_CONTENT_LENGTH"]):
                    return error_response("request_too_large", "The request exceeds the configured size limit.", 413)
            except ValueError:
                return error_response("validation_error", "Content-Length must be an integer.", 400)
        return await call_next(request)

    # ตรวจโทเคนระหว่าง Flask กับ FastAPI ซึ่งแยกจาก JWT ของผู้ใช้
    def authenticate_private_api(
        service_token: Annotated[str | None, Header(alias="X-LUMA-Service-Token")] = None,
    ) -> None:
        if not service_token or service_token != config["SERVICE_TOKEN"]:
            raise ApiError("unauthorized", "A valid service token is required.", 401)

    # ผูกการตรวจโทเคนกับ endpoint สร้างและแก้ไขภาพ

    private_api = Depends(authenticate_private_api)

    # ตรวจบริการที่พึ่งพาและส่งสถานะให้ผู้เรียกใช้ตรวจความพร้อม
    @app.get("/health", tags=["health"])
    def health():
        if is_forge_provider(config):
            try:
                forge_request(config, "GET", "/sdapi/v1/sd-models")
            except ProviderError as exc:
                return JSONResponse(
                    {
                        "status": "unavailable",
                        "service": "luma-ai",
                        "provider": "webui-forge",
                        "error": str(exc),
                        "queue": queue_manager.status(),
                    },
                    status_code=503,
                )
        return {
            "status": "ok",
            "service": "luma-ai",
            "provider": config["PROVIDER_NAME"],
            "queue": queue_manager.status(),
        }

    # ดึงรายชื่อโมเดล Checkpoints ที่มีในเครื่อง
    @app.get("/v1/models", tags=["models"], dependencies=[private_api])
    def models():
        items = scan_installed_models(config)
        return {
            "models": items,
            "count": len(items),
            "active_model": config.get("FORGE_CHECKPOINT") or (items[0]["name"] if items else None),
            "source": "local_disk" if not is_forge_provider(config) else "forge_and_disk",
        }

    # ดึงรายชื่อ LoRA พร้อมแท็กสำหรับใช้ใน Prompt
    @app.get("/v1/loras", tags=["loras"], dependencies=[private_api])
    def loras():
        items = scan_installed_loras(config)
        return {
            "loras": items,
            "count": len(items),
            "source": "local_disk" if not is_forge_provider(config) else "forge_and_disk",
        }

    # เสิร์ฟภาพพรีวิวตัวอย่างของโมเดล Checkpoint
    @app.get("/v1/preview/model/{name}", tags=["models"])
    def model_preview(name: str):
        path = find_preview_file(name, config.get("MODELS_DIR", ""))
        if not path or not path.exists():
            return error_response("not_found", f"Preview image for model '{name}' not found.", 404)
        media_type = "image/png" if path.suffix.lower() == ".png" else "image/jpeg"
        return FileResponse(str(path), media_type=media_type, headers={"Cache-Control": "public, max-age=86400"})

    # เสิร์ฟภาพพรีวิวตัวอย่างของ LoRA
    @app.get("/v1/preview/lora/{name}", tags=["loras"])
    def lora_preview(name: str):
        path = find_preview_file(name, config.get("LORAS_DIR", ""))
        if not path or not path.exists():
            return error_response("not_found", f"Preview image for LoRA '{name}' not found.", 404)
        media_type = "image/png" if path.suffix.lower() == ".png" else "image/jpeg"
        return FileResponse(str(path), media_type=media_type, headers={"Cache-Control": "public, max-age=86400"})

    # ดึงรายชื่อ Sampler ทั้งหมดที่รองรับ พร้อมหมวดหมู่และจำนวน steps แนะนำ
    @app.get("/v1/samplers", tags=["settings"], dependencies=[private_api])
    def samplers():
        items = get_supported_samplers(config)
        return {
            "samplers": items,
            "count": len(items),
            "default": config.get("FORGE_SAMPLER") or "Euler",
        }

    # ดึงรายชื่อ Scheduler สำหรับควบคุม Noise Schedule
    @app.get("/v1/schedulers", tags=["settings"], dependencies=[private_api])
    def schedulers():
        items = get_supported_schedulers(config)
        return {
            "schedulers": items,
            "count": len(items),
            "default": config.get("FORGE_SCHEDULER") or "Automatic",
        }

    # ดึงการตั้งค่าทั้งหมด: ค่ามาตรฐาน, ขอบเขตที่อนุญาต, อัตราส่วนภาพ และ Presets คุณภาพ
    @app.get("/v1/settings", tags=["settings"], dependencies=[private_api])
    def settings():
        active_checkpoint = config.get("FORGE_CHECKPOINT") or ""
        installed_models = scan_installed_models(config)
        return {
            "defaults": {
                "sampler": config.get("FORGE_SAMPLER") or "Euler",
                "scheduler": config.get("FORGE_SCHEDULER") or "Automatic",
                "cfg_scale": float(config.get("FORGE_CFG_SCALE", 7.0)),
                "steps": int(config.get("FORGE_EDIT_STEPS", 20)),
                "clip_skip": int(config.get("CLIP_SKIP", 2)),
                "width": 512,
                "height": 512,
                "active_model": active_checkpoint or (installed_models[0]["name"] if installed_models else None),
            },
            "ranges": {
                "cfg_scale": {"min": 1.0, "max": 20.0, "step": 0.5, "default": float(config.get("FORGE_CFG_SCALE", 7.0))},
                "steps": {"min": 1, "max": 50, "step": 1, "default": int(config.get("FORGE_EDIT_STEPS", 20))},
                "clip_skip": {"min": 1, "max": 12, "step": 1, "default": int(config.get("CLIP_SKIP", 2))},
                "dimensions": {"min": MIN_DIMENSION, "max": MAX_DIMENSION, "multiple_of": 64},
            },
            "aspect_ratios": ASPECT_RATIOS,
            "presets": QUALITY_PRESETS,
            "styles": STYLE_PRESETS,
            "total_models": len(installed_models),
            "total_loras": len(scan_installed_loras(config)),
        }

    # ดึงรายชื่อ Style Presets ทั้งหมดที่รองรับ พร้อมคำอธิบายและตัวปรับแต่ง Prompt
    @app.get("/v1/styles", tags=["styles"], dependencies=[private_api])
    def styles():
        categories = sorted(list({p["category"] for p in STYLE_PRESETS}))
        return {
            "styles": STYLE_PRESETS,
            "count": len(STYLE_PRESETS),
            "categories": categories,
        }

    # ดึงรายละเอียดเฉพาะของ Style Preset ตาม id
    @app.get("/v1/styles/{style_id}", tags=["styles"], dependencies=[private_api])
    def style_detail(style_id: str):
        preset = get_style_preset_by_id(style_id)
        if not preset:
            return error_response("not_found", f"Style preset '{style_id}' not found.", 404)
        return preset

    # ดึงสถานะความคืบหน้าการสร้างภาพแบบเรียลไทม์ (Live Progress) พร้อมขั้นตอนและภาพพรีวิว
    @app.get("/v1/progress", tags=["progress", "queue"], dependencies=[private_api])
    def progress(include_preview: bool = False):
        return get_live_progress(config, queue_manager, include_preview=include_preview)

    # ดึงสถานะคิวและการใช้งาน GPU แบบเรียลไทม์
    @app.get("/v1/queue/status", tags=["queue"], dependencies=[private_api])
    def queue_status():
        return queue_manager.status()

    # ขอยกเลิกงานสร้างภาพที่กำลังประมวลผลอยู่บน WebUI Forge ทันที
    @app.post("/v1/interrupt", tags=["queue"], dependencies=[private_api])
    def interrupt():
        if is_forge_provider(config):
            try:
                forge_request(config, "POST", "/sdapi/v1/interrupt")
                return {"status": "interrupted", "message": "Forge generation interrupt signal sent."}
            except ProviderUnavailable as exc:
                raise ApiError("provider_unavailable", str(exc), 503) from exc
            except ProviderError as exc:
                raise ApiError("provider_error", str(exc), 502) from exc
        return {"status": "ok", "message": "Interrupt signal processed (development provider)."}

    # ขอข้ามขั้นตอนการสร้างภาพปัจจุบันบน WebUI Forge
    @app.post("/v1/skip", tags=["queue"], dependencies=[private_api])
    def skip():
        if is_forge_provider(config):
            try:
                forge_request(config, "POST", "/sdapi/v1/skip")
                return {"status": "skipped", "message": "Forge generation skip signal sent."}
            except ProviderUnavailable as exc:
                raise ApiError("provider_unavailable", str(exc), 503) from exc
            except ProviderError as exc:
                raise ApiError("provider_error", str(exc), 502) from exc
        return {"status": "ok", "message": "Skip signal processed (development provider)."}

    # ตรวจข้อมูลสร้างภาพแล้วส่งต่อการประมวลผลตามหน้าที่ของบริการนี้
    @app.post("/v1/generate", tags=["images"], dependencies=[private_api])
    def generate(payload: GenerateRequest):
        effective_prompt, effective_neg, effective_sampler, effective_sched, effective_cfg, effective_clip, effective_steps, matched_style = apply_style_preset(
            payload.style_preset,
            payload.prompt,
            negative_prompt=payload.negative_prompt,
            sampler=payload.sampler,
            scheduler=payload.scheduler,
            cfg_scale=payload.cfg_scale,
            clip_skip=payload.clip_skip,
            steps=payload.steps,
        )
        with queue_manager.acquire(timeout=float(config["QUEUE_TIMEOUT_SECONDS"])) as job_stats:
            seed = prompt_seed(effective_prompt, payload.seed)
            try:
                if is_forge_provider(config):
                    image, seed = generate_forge_image(
                        config,
                        effective_prompt,
                        effective_neg,
                        payload.width,
                        payload.height,
                        seed,
                        effective_steps or payload.steps,
                        model=payload.model,
                        loras=payload.loras,
                        sampler=effective_sampler,
                        scheduler=effective_sched,
                        cfg_scale=effective_cfg,
                        clip_skip=effective_clip,
                    )
                else:
                    image = generate_development_image(
                        effective_prompt,
                        payload.width,
                        payload.height,
                        seed,
                        model=payload.model,
                        loras=payload.loras,
                        sampler=effective_sampler,
                        scheduler=effective_sched,
                        cfg_scale=effective_cfg,
                        clip_skip=effective_clip,
                        style_preset=matched_style["id"] if matched_style else None,
                    )
            except ProviderUnavailable as exc:
                raise ApiError("provider_unavailable", str(exc), 503) from exc
            except ProviderError as exc:
                raise ApiError("provider_error", str(exc), 502) from exc
            # ใช้บัฟเฟอร์ในหน่วยความจำแทนไฟล์ชั่วคราวสำหรับข้อมูลภาพ
            buffer = io.BytesIO()
            image.save(buffer, format="PNG", optimize=True)
            active_sampler = effective_sampler or config.get("FORGE_SAMPLER") or "Euler"
            active_cfg = effective_cfg if effective_cfg is not None else float(config.get("FORGE_CFG_SCALE", 7.0))
            current_exec_ms = round((time.perf_counter() - job_stats["exec_start"]) * 1000.0, 1)
            response_headers = {
                "Content-Disposition": f'attachment; filename="luma-{seed}.png"',
                "X-LUMA-Seed": str(seed),
                "X-LUMA-Provider": str(config["PROVIDER_NAME"]),
                "X-LUMA-Sampler": str(active_sampler),
                "X-LUMA-CFG-Scale": str(active_cfg),
                "X-LUMA-Steps": str(effective_steps or payload.steps),
                "X-LUMA-Queue-Wait-Ms": str(job_stats["wait_ms"]),
                "X-LUMA-Execution-Ms": str(current_exec_ms),
                "X-LUMA-Queue-Remaining": str(job_stats["remaining_queued"]),
            }
            if payload.model:
                response_headers["X-LUMA-Model"] = str(payload.model)
            if payload.loras:
                response_headers["X-LUMA-LoRAs"] = json.dumps(payload.loras)
            if effective_sched:
                response_headers["X-LUMA-Scheduler"] = str(effective_sched)
            if effective_clip is not None:
                response_headers["X-LUMA-Clip-Skip"] = str(effective_clip)
            if matched_style:
                response_headers["X-LUMA-Style-Preset"] = str(matched_style["id"])
            # ส่งข้อมูลภาพ PNG พร้อม seed และชื่อ provider ในส่วนหัว
            return Response(
                content=buffer.getvalue(),
                media_type="image/png",
                headers=response_headers,
            )

    # ตรวจภาพที่อัปโหลดและพารามิเตอร์แก้ไขก่อนส่งต่อการประมวลผล
    @app.post("/v1/edit", tags=["images"], dependencies=[private_api])
    def edit(
        image: Annotated[UploadFile, File(description="Source image to edit")],
        prompt: Annotated[str, Form()],
        strength_value: Annotated[str, Form(alias="strength")] = "0.65",
        seed_value: Annotated[str | None, Form(alias="seed")] = None,
        model: Annotated[str | None, Form()] = None,
        loras: Annotated[str | None, Form()] = None,
        sampler: Annotated[str | None, Form()] = None,
        scheduler: Annotated[str | None, Form()] = None,
        cfg_scale_value: Annotated[str | None, Form(alias="cfg_scale")] = None,
        clip_skip_value: Annotated[str | None, Form(alias="clip_skip")] = None,
        style_preset: Annotated[str | None, Form(alias="style_preset")] = None,
    ):
        if not image.filename:
            raise ApiError("validation_error", "An image file is required.", 400)
        try:
            parsed_prompt = parse_prompt(prompt)
            strength = float(strength_value)
            if not 0 <= strength <= 1:
                raise ValueError("Strength must be between 0 and 1.")
            seed = prompt_seed(parsed_prompt, seed_value)
            cfg_scale = float(cfg_scale_value) if cfg_scale_value not in (None, "") else None
            clip_skip = int(clip_skip_value) if clip_skip_value not in (None, "") else None
            parsed_loras = None
            if loras:
                try:
                    parsed_loras = json.loads(loras)
                except Exception:
                    parsed_loras = [name.strip() for name in loras.split(",") if name.strip()]
            image.file.seek(0, io.SEEK_END)
            if image.file.tell() > int(config["MAX_CONTENT_LENGTH"]):
                raise ApiError("request_too_large", "The request exceeds the configured size limit.", 413)
            image.file.seek(0)
            source = Image.open(image.file)
            source.verify()
            image.file.seek(0)
            source = Image.open(image.file)
            if source.width * source.height > MAX_DIMENSION * MAX_DIMENSION * 4:
                raise ValueError("The input image has too many pixels.")
        except ApiError:
            raise
        except (ValueError, UnidentifiedImageError) as exc:
            raise ApiError("validation_error", str(exc) or "The uploaded file is not a valid image.", 400) from exc

        effective_prompt, _, effective_sampler, effective_sched, effective_cfg, effective_clip, _, matched_style = apply_style_preset(
            style_preset,
            parsed_prompt,
            sampler=sampler,
            scheduler=scheduler,
            cfg_scale=cfg_scale,
            clip_skip=clip_skip,
        )

        with queue_manager.acquire(timeout=float(config["QUEUE_TIMEOUT_SECONDS"])) as job_stats:
            try:
                if is_forge_provider(config):
                    result, seed = edit_forge_image(
                        config,
                        source,
                        effective_prompt,
                        strength,
                        seed,
                        model=model,
                        loras=parsed_loras,
                        sampler=effective_sampler,
                        scheduler=effective_sched,
                        cfg_scale=effective_cfg,
                        clip_skip=effective_clip,
                    )
                else:
                    result = edit_development_image(
                        source,
                        effective_prompt,
                        strength,
                        seed,
                        model=model,
                        loras=parsed_loras,
                        sampler=effective_sampler,
                        scheduler=effective_sched,
                        cfg_scale=effective_cfg,
                        clip_skip=effective_clip,
                        style_preset=matched_style["id"] if matched_style else None,
                    )
            except ProviderUnavailable as exc:
                raise ApiError("provider_unavailable", str(exc), 503) from exc
            except ProviderError as exc:
                raise ApiError("provider_error", str(exc), 502) from exc
            buffer = io.BytesIO()
            result.save(buffer, format="PNG", optimize=True)
            active_sampler = effective_sampler or config.get("FORGE_SAMPLER") or "Euler"
            active_cfg = effective_cfg if effective_cfg is not None else float(config.get("FORGE_CFG_SCALE", 7.0))
            current_exec_ms = round((time.perf_counter() - job_stats["exec_start"]) * 1000.0, 1)
            response_headers = {
                "Content-Disposition": f'attachment; filename="luma-edit-{seed}.png"',
                "X-LUMA-Seed": str(seed),
                "X-LUMA-Provider": str(config["PROVIDER_NAME"]),
                "X-LUMA-Sampler": str(active_sampler),
                "X-LUMA-CFG-Scale": str(active_cfg),
                "X-LUMA-Queue-Wait-Ms": str(job_stats["wait_ms"]),
                "X-LUMA-Execution-Ms": str(current_exec_ms),
                "X-LUMA-Queue-Remaining": str(job_stats["remaining_queued"]),
            }
            if model:
                response_headers["X-LUMA-Model"] = str(model)
            if parsed_loras:
                response_headers["X-LUMA-LoRAs"] = json.dumps(parsed_loras)
            if effective_sched:
                response_headers["X-LUMA-Scheduler"] = str(effective_sched)
            if effective_clip is not None:
                response_headers["X-LUMA-Clip-Skip"] = str(effective_clip)
            if matched_style:
                response_headers["X-LUMA-Style-Preset"] = str(matched_style["id"])
            return Response(
                content=buffer.getvalue(),
                media_type="image/png",
                headers=response_headers,
            )


    return app


app = create_app()

# เริ่มบริการหรือคำสั่งเฉพาะเมื่อรันไฟล์นี้โดยตรง

if __name__ == "__main__":
    import uvicorn

    # ให้ Uvicorn เปิด FastAPI บน host และพอร์ตที่กำหนด

    uvicorn.run(
        "app:app",
        host=os.getenv("HOST", "127.0.0.1"),
        port=int(os.getenv("PORT", "8000")),
        reload=os.getenv("FASTAPI_DEBUG", "0") == "1",
    )

