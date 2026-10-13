# โมดูลเชื่อมต่อและส่งคำขอไปยัง WebUI Forge (Stable Diffusion)
"""WebUI Forge client integration for LUMA AI Engine."""

from __future__ import annotations

import base64
import io
import json
import time
from pathlib import Path
from typing import Any

import requests
from PIL import Image, ImageOps, UnidentifiedImageError

try:
    from .exceptions import ProviderError, ProviderUnavailable
    from .validators import MAX_DIMENSION
except (ImportError, ValueError):
    from exceptions import ProviderError, ProviderUnavailable
    from validators import MAX_DIMENSION


# ตรวจชื่อ provider ว่าต้องเรียก Forge หรือใช้ตัวสร้างภาพทดสอบ
def is_forge_provider(config: dict[str, Any]) -> bool:
    return str(config.get("PROVIDER_NAME", "")).casefold() in {"forge", "webui-forge", "stable-diffusion-webui-forge"}


# สร้างข้อมูล HTTP Basic Auth เมื่อ Forge กำหนดชื่อผู้ใช้ไว้
def forge_auth(config: dict[str, Any]):
    username = str(config.get("FORGE_USERNAME", ""))
    password = str(config.get("FORGE_PASSWORD", ""))
    return (username, password) if username else None


# เรียก Forge ด้วยเวลารอที่กำหนด และแปลงปัญหาเครือข่ายหรือ HTTP เป็นข้อผิดพลาด provider
def _real_forge_request(config: dict[str, Any], method: str, endpoint: str, **kwargs) -> requests.Response:
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


# เรียก Forge ด้วยเวลารอที่กำหนด และแปลงปัญหาเครือข่ายหรือ HTTP เป็นข้อผิดพลาด provider
def forge_request(config: dict[str, Any], method: str, endpoint: str, **kwargs) -> requests.Response:
    import sys

    for mod_name in ("app", "luma_ai_app", "__main__"):
        mod = sys.modules.get(mod_name)
        if mod and hasattr(mod, "forge_request"):
            fn = getattr(mod, "forge_request")
            if fn is not forge_request and fn is not _real_forge_request:
                return fn(config, method, endpoint, **kwargs)
    return _real_forge_request(config, method, endpoint, **kwargs)


_forge_models_cache: dict[str, Any] = {"timestamp": 0.0, "models": []}


def get_forge_model_title(config: dict[str, Any], requested: str | None) -> str | None:
    if not requested:
        return None
    now = time.time()
    if now - float(_forge_models_cache.get("timestamp", 0.0)) > 60.0 or not _forge_models_cache.get("models"):
        try:
            resp = forge_request(config, "GET", "/sdapi/v1/sd-models")
            if resp.ok and isinstance(resp.json(), list):
                _forge_models_cache["models"] = resp.json()
                _forge_models_cache["timestamp"] = now
        except Exception:
            pass
    req_clean = requested.casefold().replace(".safetensors", "").replace(".ckpt", "").strip()
    for m in _forge_models_cache.get("models", []):
        title = m.get("title", "")
        model_name = m.get("model_name", "")
        filename_stem = Path(m.get("filename", "")).stem.casefold()
        if (
            req_clean == title.casefold()
            or req_clean == model_name.casefold()
            or req_clean == filename_stem
            or req_clean in title.casefold()
        ):
            return title
    return requested


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

    cfg = float(cfg_scale) if cfg_scale is not None else float(config.get("FORGE_CFG_SCALE", 7.0))
    sampler_name = sampler or config.get("FORGE_SAMPLER", "Euler")

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
    raw_checkpoint = model or config.get("FORGE_CHECKPOINT")
    if raw_checkpoint:
        resolved_title = get_forge_model_title(config, raw_checkpoint)
        override_settings["sd_model_checkpoint"] = resolved_title or raw_checkpoint
    if clip_skip is not None:
        override_settings["CLIP_stop_at_last_layers"] = int(clip_skip)

    if override_settings:
        payload["override_settings"] = override_settings
        payload["override_settings_restore_afterwards"] = False
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
        int(config.get("FORGE_EDIT_STEPS", 20)),
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


# ส่งภาพไปยัง WebUI Forge เพื่อถอดคำบรรยายหรือแท็กด้วย DeepDanbooru หรือ CLIP
def interrogate_forge_image(
    config: dict[str, Any],
    source: Image.Image,
    model: str = "deepdanbooru",
) -> str:
    image = ImageOps.exif_transpose(source).convert("RGB")
    image.thumbnail((MAX_DIMENSION, MAX_DIMENSION), Image.Resampling.LANCZOS)
    source_buffer = io.BytesIO()
    image.save(source_buffer, format="PNG")
    b64_image = base64.b64encode(source_buffer.getvalue()).decode("ascii")
    payload = {
        "image": f"data:image/png;base64,{b64_image}",
        "model": model,
    }
    response = forge_request(config, "POST", "/sdapi/v1/interrogate", json=payload)
    try:
        data = response.json()
        caption = str(data.get("caption") or "").strip()
        return caption
    except Exception as exc:
        raise ProviderError(f"WebUI Forge returned invalid interrogate response: {response.text[:200]}") from exc


# ส่งภาพไปยัง WebUI Forge เพื่อขยายความละเอียดด้วย AI Upscaler
def upscale_forge_image(
    config: dict[str, Any],
    source: Image.Image,
    scale_factor: float = 2.0,
    upscaler: str = "R-ESRGAN 4x+",
) -> Image.Image:
    image = ImageOps.exif_transpose(source).convert("RGB")
    source_buffer = io.BytesIO()
    image.save(source_buffer, format="PNG")
    b64_image = base64.b64encode(source_buffer.getvalue()).decode("ascii")

    payload = {
        "image": f"data:image/png;base64,{b64_image}",
        "resize_mode": 0,
        "upscaling_resize": float(scale_factor),
        "upscaler_1": upscaler,
    }
    response = forge_request(config, "POST", "/sdapi/v1/extra-single-image", json=payload)
    try:
        data = response.json()
        b64_result = data.get("image")
        if not b64_result:
            raise ProviderError("WebUI Forge returned empty upscale image data.")
        if "," in b64_result:
            b64_result = b64_result.split(",", 1)[1]
        decoded = base64.b64decode(b64_result)
        upscaled_image = Image.open(io.BytesIO(decoded)).convert("RGB")
        return upscaled_image
    except ProviderError:
        raise
    except Exception as exc:
        raise ProviderError(f"Failed to decode WebUI Forge upscale response: {str(exc)[:200]}") from exc
