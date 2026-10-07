# บริการ FastAPI เชื่อม Forge และ provider ภาพทดสอบ (LUMA AI Engine Entry Point)
"""Private LUMA image service with WebUI Forge and development providers.

This module acts as the FastAPI application entry point, routing requests to
modular services:
- exceptions: Custom API and provider exceptions
- queue_manager: Thread-safe GPU concurrency and queue manager
- validators: Request validation models and parsing utilities
- styles: Curated style presets and prompt enhancement
- forge_client: WebUI Forge API integration
- scanner: Model/LoRA filesystem and API scanner and catalog presets
- filters: Image processing filter algorithms (ITU-R BT.601, Laplacian, Gaussian blur, invert)
- dev_provider: Procedural development image generator and simulator
"""

from __future__ import annotations

import io
import json
import logging
import os
import sys
import time
from pathlib import Path
from typing import Annotated, Any

# Ensure ai-engine folder is in sys.path for both package and direct/spec loading
_AI_ENGINE_DIR = str(Path(__file__).resolve().parent)
if _AI_ENGINE_DIR not in sys.path:
    sys.path.insert(0, _AI_ENGINE_DIR)

import requests
from dotenv import load_dotenv
from fastapi import Depends, FastAPI, File, Form, Header, Request, UploadFile
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse, Response
from PIL import Image, UnidentifiedImageError
from PIL.PngImagePlugin import PngInfo
from starlette.exceptions import HTTPException as StarletteHTTPException

try:
    from png_parser import parse_png_parameters
except ImportError:
    from .png_parser import parse_png_parameters

try:
    from tag_service import search_tags
except ImportError:
    from .tag_service import search_tags

# โหลดค่าจาก .env ก่อนสร้างแอปหรืออ่าน environment
load_dotenv()

# นำเข้าโมดูลที่แยกย่อยและ Re-export สำหรับ backwards compatibility
try:
    from exceptions import ApiError, ProviderError, ProviderUnavailable
except ImportError:
    from .exceptions import ApiError, ProviderError, ProviderUnavailable

try:
    from queue_manager import GenerationQueueManager
except ImportError:
    from .queue_manager import GenerationQueueManager

try:
    from validators import (
        MAX_DIMENSION,
        MAX_PROMPT_LENGTH,
        MIN_DIMENSION,
        GenerateRequest,
        error_response,
        parse_integer,
        parse_prompt,
        prompt_seed,
        validation_message,
    )
except ImportError:
    from .validators import (
        MAX_DIMENSION,
        MAX_PROMPT_LENGTH,
        MIN_DIMENSION,
        GenerateRequest,
        error_response,
        parse_integer,
        parse_prompt,
        prompt_seed,
        validation_message,
    )

try:
    from styles import (
        STYLE_PRESETS,
        apply_style_preset,
        get_style_preset_by_id,
    )
except ImportError:
    from .styles import (
        STYLE_PRESETS,
        apply_style_preset,
        get_style_preset_by_id,
    )

try:
    from forge_client import (
        decode_forge_image,
        edit_forge_image,
        forge_auth,
        forge_payload,
        forge_request,
        generate_forge_image,
        interrogate_forge_image,
        is_forge_provider,
        upscale_forge_image,
    )
except ImportError:
    from .forge_client import (
        decode_forge_image,
        edit_forge_image,
        forge_auth,
        forge_payload,
        forge_request,
        generate_forge_image,
        interrogate_forge_image,
        is_forge_provider,
        upscale_forge_image,
    )

try:
    from scanner import (
        ASPECT_RATIOS,
        DEFAULT_SAMPLERS,
        DEFAULT_SCHEDULERS,
        DEFAULT_UPSCALERS,
        QUALITY_PRESETS,
        find_preview_file,
        get_supported_samplers,
        get_supported_schedulers,
        get_supported_upscalers,
        read_cm_info,
        scan_installed_loras,
        scan_installed_models,
    )
except ImportError:
    from .scanner import (
        ASPECT_RATIOS,
        DEFAULT_SAMPLERS,
        DEFAULT_SCHEDULERS,
        DEFAULT_UPSCALERS,
        QUALITY_PRESETS,
        find_preview_file,
        get_supported_samplers,
        get_supported_schedulers,
        get_supported_upscalers,
        read_cm_info,
        scan_installed_loras,
        scan_installed_models,
    )

try:
    from filters import (
        ALLOWED_FILTER_CONTENT_TYPES,
        FILTER_OPERATIONS,
        process_filter_image,
    )
except ImportError:
    from .filters import (
        ALLOWED_FILTER_CONTENT_TYPES,
        FILTER_OPERATIONS,
        process_filter_image,
    )

try:
    from dev_provider import (
        _palette,
        edit_development_image,
        generate_development_image,
        get_live_progress,
        interrogate_development_image,
        upscale_development_image,
    )
except ImportError:
    from .dev_provider import (
        _palette,
        edit_development_image,
        generate_development_image,
        get_live_progress,
        interrogate_development_image,
        upscale_development_image,
    )

# Re-export all public symbols for backwards compatibility
__all__ = [
    "ALLOWED_FILTER_CONTENT_TYPES",
    "ASPECT_RATIOS",
    "ApiError",
    "DEFAULT_SAMPLERS",
    "DEFAULT_SCHEDULERS",
    "DEFAULT_UPSCALERS",
    "FILTER_OPERATIONS",
    "GenerateRequest",
    "GenerationQueueManager",
    "MAX_DIMENSION",
    "MAX_PROMPT_LENGTH",
    "MIN_DIMENSION",
    "ProviderError",
    "ProviderUnavailable",
    "QUALITY_PRESETS",
    "STYLE_PRESETS",
    "_palette",
    "app",
    "apply_style_preset",
    "create_app",
    "decode_forge_image",
    "edit_development_image",
    "edit_forge_image",
    "error_response",
    "find_preview_file",
    "forge_auth",
    "forge_payload",
    "forge_request",
    "generate_development_image",
    "generate_forge_image",
    "get_live_progress",
    "get_style_preset_by_id",
    "get_supported_samplers",
    "get_supported_schedulers",
    "get_supported_upscalers",
    "interrogate_development_image",
    "interrogate_forge_image",
    "is_forge_provider",
    "parse_integer",
    "parse_prompt",
    "process_filter_image",
    "prompt_seed",
    "read_cm_info",
    "requests",
    "scan_installed_loras",
    "scan_installed_models",
    "upscale_development_image",
    "upscale_forge_image",
    "validation_message",
]


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
        detail = error.detail if isinstance(error.detail, str) else "An unexpected error occurred."
        return error_response("http_error", detail, error.status_code)

    # ตรวจขนาดข้อมูลคำขอไม่ให้เกินขีดจำกัดที่กำหนดไว้
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
            "upscalers": get_supported_upscalers(config),
            "default_upscaler": config.get("FORGE_UPSCALER") or "R-ESRGAN 4x+",
            "interrogators": [
                {"id": "deepdanbooru", "name": "DeepDanbooru", "output_format": "tags"},
                {"id": "clip", "name": "CLIP / BLIP", "output_format": "prose"},
            ],
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

            # ใช้บัฟเฟอร์ในหน่วยความจำและฝัง Generation Metadata (PNG Info) ลงในไฟล์ภาพ
            buffer = io.BytesIO()
            active_sampler = effective_sampler or config.get("FORGE_SAMPLER") or "Euler"
            active_cfg = effective_cfg if effective_cfg is not None else float(config.get("FORGE_CFG_SCALE", 7.0))
            active_model = payload.model or config.get("FORGE_CHECKPOINT") or "SDXL"

            pnginfo = PngInfo()
            param_parts = [effective_prompt]
            if payload.negative_prompt:
                param_parts.append(f"Negative prompt: {payload.negative_prompt}")
            setting_parts = [
                f"Steps: {effective_steps or payload.steps}",
                f"Sampler: {active_sampler}",
            ]
            if effective_sched:
                setting_parts.append(f"Schedule type: {effective_sched}")
            setting_parts.extend([
                f"CFG scale: {active_cfg}",
                f"Seed: {seed}",
                f"Size: {payload.width}x{payload.height}",
                f"Model: {active_model}",
            ])
            param_parts.append(", ".join(setting_parts))
            pnginfo.add_text("parameters", "\n".join(param_parts))

            image.save(buffer, format="PNG", pnginfo=pnginfo, optimize=True)
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

    # ดึงรายชื่อโมเดล Interrogator ที่รองรับ
    @app.get("/v1/interrogate/models", tags=["images", "interrogate"], dependencies=[private_api])
    def interrogate_models():
        return {
            "models": [
                {
                    "id": "deepdanbooru",
                    "name": "DeepDanbooru",
                    "description": "Booru anime tags format (e.g. 1girl, solo, blue eyes). Best for anime/manga models.",
                    "output_format": "tags",
                },
                {
                    "id": "clip",
                    "name": "CLIP / BLIP",
                    "description": "Natural language descriptive sentence. Best for photorealistic and general concepts.",
                    "output_format": "prose",
                },
            ],
            "default": "deepdanbooru",
        }

    # ถอดคำบรรยายหรือแท็ก Danbooru จากภาพอ้างอิงด้วย DeepDanbooru หรือ CLIP
    @app.post("/v1/interrogate", tags=["images", "interrogate"], dependencies=[private_api])
    def interrogate(
        image: Annotated[UploadFile, File(description="Source image to interrogate")],
        model: Annotated[str, Form(description="Interrogator model: deepdanbooru or clip")] = "deepdanbooru",
    ):
        if not image.filename:
            raise ApiError("validation_error", "An image file is required.", 400)
        try:
            interrogate_model = str(model or "deepdanbooru").strip().lower()
            if interrogate_model not in {"deepdanbooru", "clip"}:
                raise ValueError("Model must be 'deepdanbooru' or 'clip'.")

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

        with queue_manager.acquire(timeout=float(config["QUEUE_TIMEOUT_SECONDS"])) as job_stats:
            try:
                if is_forge_provider(config):
                    caption = interrogate_forge_image(config, source, model=interrogate_model)
                else:
                    caption = interrogate_development_image(source, model=interrogate_model)
            except ProviderUnavailable as exc:
                raise ApiError("provider_unavailable", str(exc), 503) from exc
            except ProviderError as exc:
                raise ApiError("provider_error", str(exc), 502) from exc

            current_exec_ms = round((time.perf_counter() - job_stats["exec_start"]) * 1000.0, 1)
            tags = [t.strip() for t in caption.split(",") if t.strip()]

            response_headers = {
                "X-LUMA-Provider": str(config["PROVIDER_NAME"]),
                "X-LUMA-Model": interrogate_model,
                "X-LUMA-Queue-Wait-Ms": str(job_stats["wait_ms"]),
                "X-LUMA-Execution-Ms": str(current_exec_ms),
            }
            return JSONResponse(
                content={
                    "status": "ok",
                    "model": interrogate_model,
                    "caption": caption,
                    "tags": tags,
                    "provider": config["PROVIDER_NAME"],
                    "execution_ms": current_exec_ms,
                },
                headers=response_headers,
            )

    # ดึงรายชื่อ AI Upscalers ที่ระบบรองรับ
    @app.get("/v1/upscalers", tags=["images", "upscale"], dependencies=[private_api])
    def upscalers():
        items = get_supported_upscalers(config)
        default_upscaler = config.get("FORGE_UPSCALER") or "R-ESRGAN 4x+"
        return {
            "upscalers": items,
            "count": len(items),
            "default": default_upscaler,
            "supported_scales": [1.5, 2.0, 3.0, 4.0],
        }

    # ขยายความละเอียดและเพิ่มรายละเอียดภาพด้วย AI Upscaler (High-Res Fix / Super Resolution)
    @app.post("/v1/upscale", tags=["images", "upscale"], dependencies=[private_api])
    def upscale(
        image: Annotated[UploadFile, File(description="Source image to upscale")],
        scale_factor: Annotated[str, Form(alias="scale_factor")] = "2.0",
        upscaler: Annotated[str | None, Form()] = None,
    ):
        if not image.filename:
            raise ApiError("validation_error", "An image file is required.", 400)
        try:
            scale = float(scale_factor)
            if not 1.0 <= scale <= 4.0:
                raise ValueError("Scale factor must be between 1.0 and 4.0.")
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
            if source.width * scale > 4096 or source.height * scale > 4096:
                raise ValueError(f"Upscaling by {scale}x would exceed maximum allowable dimensions (4096px).")
        except ApiError:
            raise
        except (ValueError, UnidentifiedImageError) as exc:
            raise ApiError("validation_error", str(exc) or "The uploaded file is not a valid image.", 400) from exc

        effective_upscaler = (upscaler or config.get("FORGE_UPSCALER") or "R-ESRGAN 4x+").strip()

        with queue_manager.acquire(timeout=float(config["QUEUE_TIMEOUT_SECONDS"])) as job_stats:
            try:
                if is_forge_provider(config):
                    result = upscale_forge_image(
                        config,
                        source,
                        scale_factor=scale,
                        upscaler=effective_upscaler,
                    )
                else:
                    result = upscale_development_image(
                        source,
                        scale_factor=scale,
                        upscaler=effective_upscaler,
                    )
            except ProviderUnavailable as exc:
                raise ApiError("provider_unavailable", str(exc), 503) from exc
            except ProviderError as exc:
                raise ApiError("provider_error", str(exc), 502) from exc

            buffer = io.BytesIO()
            result.save(buffer, format="PNG", optimize=True)
            current_exec_ms = round((time.perf_counter() - job_stats["exec_start"]) * 1000.0, 1)

            response_headers = {
                "Content-Disposition": f'attachment; filename="luma-upscale-{result.width}x{result.height}.png"',
                "X-LUMA-Provider": str(config["PROVIDER_NAME"]),
                "X-LUMA-Upscaler": effective_upscaler,
                "X-LUMA-Scale": str(scale),
                "X-LUMA-Width": str(result.width),
                "X-LUMA-Height": str(result.height),
                "X-LUMA-Queue-Wait-Ms": str(job_stats["wait_ms"]),
                "X-LUMA-Execution-Ms": str(current_exec_ms),
                "X-LUMA-Queue-Remaining": str(job_stats["remaining_queued"]),
            }
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

    # ดึงรายชื่อ Filter และ Image Processing Operations ที่ระบบรองรับ (API_Workshop compatible)
    @app.get("/v1/filters", tags=["images", "filters"])
    @app.get("/filters", tags=["images", "filters"])
    def get_supported_filters():
        return {
            "operations": [
                {
                    "id": "grayscale",
                    "name": "Grayscale",
                    "algorithm": "Luminance Weighted Sum (ITU-R BT.601: 0.299R + 0.587G + 0.114B)",
                    "description": "Convert RGB to monochrome luminance channel.",
                },
                {
                    "id": "edge",
                    "name": "Edge Detection",
                    "algorithm": "Spatial 2D Convolution Kernel Filter (Laplacian / FIND_EDGES)",
                    "description": "Detect high-gradient boundaries and contours for ControlNet lineart.",
                },
                {
                    "id": "blur",
                    "name": "Gaussian Blur",
                    "algorithm": "2D Gaussian Kernel Smoothing (radius=4)",
                    "description": "Low-pass spatial filter for noise reduction and smoothing.",
                },
                {
                    "id": "invert",
                    "name": "Color Inversion",
                    "algorithm": "Arithmetic Channel Inversion (255 - X)",
                    "description": "Negative color transformation.",
                },
            ],
            "default": "grayscale",
        }

    # ประมวลผลภาพ (Grayscale, Edge Detection, Blur, Invert) ตามมาตรฐาน API_Workshop
    @app.post(
        "/process",
        tags=["images", "filters"],
        response_class=Response,
        responses={200: {"content": {"image/png": {}}}},
    )
    @app.post(
        "/v1/process",
        tags=["images", "filters"],
        response_class=Response,
        responses={200: {"content": {"image/png": {}}}},
    )
    @app.post(
        "/v1/filters/process",
        tags=["images", "filters"],
        response_class=Response,
        responses={200: {"content": {"image/png": {}}}},
    )
    async def process_image_endpoint(
        file: UploadFile = File(description="Source image file (JPEG, PNG, WebP)"),
        operation: Annotated[str, Form(description="Operation: grayscale, edge, blur, invert")] = "grayscale",
    ) -> Response:
        """ตรวจสอบไฟล์ ใช้ operation ที่ร้องขอ และตอบกลับเป็นภาพ PNG (API_Workshop compatible)."""
        # ตรวจ MIME type เบื้องต้น
        if file.content_type and file.content_type not in ALLOWED_FILTER_CONTENT_TYPES:
            raise ApiError("unsupported_media_type", "รองรับเฉพาะไฟล์ JPEG, PNG และ WebP", 415)

        op = str(operation or "grayscale").strip().lower()
        if op not in FILTER_OPERATIONS:
            raise ApiError(
                "validation_error",
                f"ไม่รู้จักรูปแบบการประมวลผล '{op}'. รองรับเฉพาะ: {', '.join(sorted(FILTER_OPERATIONS))}",
                400,
            )

        max_size = int(config.get("MAX_CONTENT_LENGTH", 10 * 1024 * 1024))
        file_bytes = await file.read(max_size + 1)
        await file.close()

        if not file_bytes:
            raise ApiError("validation_error", "ไฟล์ภาพว่างเปล่า", 400)
        if len(file_bytes) > max_size:
            raise ApiError("request_too_large", "ไฟล์ภาพต้องมีขนาดไม่เกิน 10 MB", 413)

        try:
            with Image.open(io.BytesIO(file_bytes)) as source_image:
                source_image.load()
                result_image = process_filter_image(source_image, op)
        except (UnidentifiedImageError, OSError, ValueError) as exc:
            raise ApiError("validation_error", f"ไม่สามารถอ่านหรือประมวลผลภาพนี้ได้: {exc}", 400) from exc

        output = io.BytesIO()
        result_image.save(output, format="PNG")
        output_bytes = output.getvalue()

        return Response(
            content=output_bytes,
            media_type="image/png",
            headers={
                "Content-Disposition": f'inline; filename="processed-{op}.png"',
                "X-Image-Operation": op,
                "X-LUMA-Operation": op,
                "X-LUMA-Width": str(result_image.width),
                "X-LUMA-Height": str(result_image.height),
            },
        )

    # ดึงข้อมูล Generation Metadata จากภาพ (Prompt, Negative Prompt, Settings)
    @app.post(
        "/v1/png-info",
        tags=["images", "metadata"],
    )
    async def get_png_info_endpoint(
        file: UploadFile = File(description="Source image file to extract generation metadata from"),
    ) -> dict[str, Any]:
        """Extract generation parameters (Prompt, Negative prompt, Steps, Sampler, Seed, etc.) from an image."""
        max_size = 20 * 1024 * 1024
        file_bytes = await file.read(max_size + 1)
        await file.close()

        if not file_bytes:
            raise ApiError("validation_error", "File is empty", 400)

        try:
            with Image.open(io.BytesIO(file_bytes)) as img:
                raw_params = img.info.get("parameters") or img.text.get("parameters") or ""
                if not raw_params:
                    for k, v in img.info.items():
                        if isinstance(v, str) and ("Steps:" in v or "Negative prompt:" in v):
                            raw_params = v
                            break

                parsed = parse_png_parameters(raw_params) if raw_params else {}
                return {
                    "has_metadata": bool(raw_params),
                    "raw_parameters": raw_params,
                    "parsed": parsed,
                    "format": img.format,
                    "width": img.width,
                    "height": img.height,
                }
        except (UnidentifiedImageError, OSError, ValueError) as exc:
            raise ApiError("validation_error", f"Could not read image metadata: {exc}", 400) from exc

    # ค้นหาแท็ก Danbooru สำหรับระบบ Tag Auto-Complete
    @app.get("/v1/tags", tags=["tags"])
    def get_tags_endpoint(q: str = "", limit: int = 20) -> dict[str, Any]:
        """Search Danbooru tag suggestions for prompt autocomplete."""
        query = str(q or "").strip().lower()
        results = search_tags(query, limit=min(limit, 50))
        return {"tags": results, "count": len(results), "query": query}

    return app


# อินสแตนซ์หลักระดับโมดูลสำหรับเรียกใช้งานผ่าน ASGI server (e.g., uvicorn app:app)
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
