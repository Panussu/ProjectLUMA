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
from typing import Any

import requests
from dotenv import load_dotenv
from flask import Flask, jsonify, request, send_file
from PIL import Image, ImageChops, ImageDraw, ImageEnhance, ImageFilter, ImageFont, ImageOps, UnidentifiedImageError

load_dotenv()

MAX_DIMENSION = 1024
MIN_DIMENSION = 256
MAX_PROMPT_LENGTH = 1000


class ProviderError(RuntimeError):
    """The configured image provider returned an invalid response."""


class ProviderUnavailable(ProviderError):
    """The configured image provider could not be reached."""


def error_response(code: str, message: str, status: int):
    return jsonify({"error": {"code": code, "message": message}}), status


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


def parse_prompt(value: Any) -> str:
    prompt = str(value or "").strip()
    if not 3 <= len(prompt) <= MAX_PROMPT_LENGTH:
        raise ValueError("Prompt must contain between 3 and 1000 characters.")
    return prompt


def prompt_seed(prompt: str, supplied_seed: Any = None) -> int:
    if supplied_seed not in (None, ""):
        return parse_integer(supplied_seed, "seed", 0, 4_294_967_295)
    digest = hashlib.sha256(prompt.encode("utf-8")).digest()
    return int.from_bytes(digest[:4], "big")


def is_forge_provider(config: dict[str, Any]) -> bool:
    return str(config["PROVIDER_NAME"]).casefold() in {"forge", "webui-forge", "stable-diffusion-webui-forge"}


def forge_auth(config: dict[str, Any]):
    username = str(config.get("FORGE_USERNAME", ""))
    password = str(config.get("FORGE_PASSWORD", ""))
    return (username, password) if username else None


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
    if not response.ok:
        try:
            detail = response.json().get("detail") or response.json().get("error") or response.text
        except (ValueError, AttributeError):
            detail = response.text
        raise ProviderError(f"WebUI Forge returned HTTP {response.status_code}: {str(detail)[:300]}")
    return response


def forge_payload(config: dict[str, Any], prompt: str, seed: int, steps: int) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "prompt": prompt,
        "seed": seed,
        "steps": steps,
        "cfg_scale": float(config["FORGE_CFG_SCALE"]),
        "sampler_name": config["FORGE_SAMPLER"],
        "batch_size": 1,
        "n_iter": 1,
        "send_images": True,
        "save_images": False,
    }
    if config.get("FORGE_SCHEDULER"):
        payload["scheduler"] = config["FORGE_SCHEDULER"]
    if config.get("FORGE_CHECKPOINT"):
        payload["override_settings"] = {"sd_model_checkpoint": config["FORGE_CHECKPOINT"]}
        payload["override_settings_restore_afterwards"] = True
    return payload


def decode_forge_image(response: requests.Response, fallback_seed: int) -> tuple[Image.Image, int]:
    try:
        data = response.json()
        encoded = data["images"][0]
        if "," in encoded:
            encoded = encoded.split(",", 1)[1]
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


def generate_forge_image(
    config: dict[str, Any],
    prompt: str,
    negative_prompt: str,
    width: int,
    height: int,
    seed: int,
    steps: int,
) -> tuple[Image.Image, int]:
    payload = forge_payload(config, prompt, seed, steps)
    payload.update({"negative_prompt": negative_prompt, "width": width, "height": height})
    response = forge_request(config, "POST", "/sdapi/v1/txt2img", json=payload)
    return decode_forge_image(response, seed)


def edit_forge_image(
    config: dict[str, Any], source: Image.Image, prompt: str, strength: float, seed: int
) -> tuple[Image.Image, int]:
    image = ImageOps.exif_transpose(source).convert("RGB")
    image.thumbnail((MAX_DIMENSION, MAX_DIMENSION), Image.Resampling.LANCZOS)
    source_buffer = io.BytesIO()
    image.save(source_buffer, format="PNG")
    payload = forge_payload(config, prompt, seed, int(config["FORGE_EDIT_STEPS"]))
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


def _palette(rng: random.Random) -> list[tuple[int, int, int]]:
    base = rng.randrange(360)

    def hsl(hue: float, saturation: float, lightness: float) -> tuple[int, int, int]:
        import colorsys

        red, green, blue = colorsys.hls_to_rgb((hue % 360) / 360, lightness, saturation)
        return int(red * 255), int(green * 255), int(blue * 255)

    return [hsl(base, 0.64, 0.13), hsl(base + 48, 0.72, 0.42), hsl(base + 168, 0.58, 0.55), hsl(base + 290, 0.68, 0.63)]


def generate_development_image(prompt: str, width: int, height: int, seed: int) -> Image.Image:
    rng = random.Random(seed)
    palette = _palette(rng)
    image = Image.new("RGB", (width, height), palette[0])
    draw = ImageDraw.Draw(image, "RGBA")

    for y in range(height):
        ratio = y / max(height - 1, 1)
        start, end = palette[0], palette[1]
        color = tuple(int(start[channel] * (1 - ratio) + end[channel] * ratio) for channel in range(3))
        draw.line((0, y, width, y), fill=(*color, 255))

    for _ in range(28):
        radius = rng.randint(max(18, width // 16), max(40, width // 3))
        x = rng.randint(-radius, width + radius)
        y = rng.randint(-radius, height + radius)
        color = rng.choice(palette[1:])
        alpha = rng.randint(30, 125)
        draw.ellipse((x - radius, y - radius, x + radius, y + radius), fill=(*color, alpha))

    for _ in range(10):
        points = [(rng.randint(0, width), rng.randint(0, height)) for _ in range(rng.randint(3, 7))]
        color = rng.choice(palette)
        draw.polygon(points, fill=(*color, rng.randint(18, 55)))

    image = image.filter(ImageFilter.GaussianBlur(radius=max(2, width // 170)))
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
    overlay_draw.text((margin * 1.6, height - margin * 1.7), f"LUMA DEV PROVIDER  /  SEED {seed}", font=ImageFont.load_default(), fill=(190, 180, 230, 210))
    return Image.alpha_composite(image.convert("RGBA"), overlay).convert("RGB")


def edit_development_image(source: Image.Image, prompt: str, strength: float, seed: int) -> Image.Image:
    image = ImageOps.exif_transpose(source).convert("RGB")
    image.thumbnail((MAX_DIMENSION, MAX_DIMENSION), Image.Resampling.LANCZOS)
    rng = random.Random(seed)
    words = prompt.casefold()

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

    tint = Image.new("RGB", transformed.size, _palette(rng)[2])
    tinted = Image.blend(transformed, tint, strength * 0.18)
    texture = Image.effect_noise(transformed.size, 10 + strength * 22).convert("RGB")
    textured = ImageChops.soft_light(tinted, texture)
    return Image.blend(image, textured, strength)


def create_app(test_config: dict[str, Any] | None = None) -> Flask:
    app = Flask(__name__)
    app.config.from_mapping(
        MAX_CONTENT_LENGTH=int(os.getenv("MAX_CONTENT_LENGTH", str(16 * 1024 * 1024))),
        SERVICE_TOKEN=os.getenv("AI_SERVICE_TOKEN", "change-me-in-production"),
        PROVIDER_NAME=os.getenv("AI_PROVIDER", "development-procedural"),
        FORGE_URL=os.getenv("FORGE_URL", "http://127.0.0.1:7860"),
        FORGE_USERNAME=os.getenv("FORGE_USERNAME", ""),
        FORGE_PASSWORD=os.getenv("FORGE_PASSWORD", ""),
        FORGE_CHECKPOINT=os.getenv("FORGE_CHECKPOINT", ""),
        FORGE_SAMPLER=os.getenv("FORGE_SAMPLER", "Euler"),
        FORGE_SCHEDULER=os.getenv("FORGE_SCHEDULER", ""),
        FORGE_CFG_SCALE=float(os.getenv("FORGE_CFG_SCALE", "7")),
        FORGE_EDIT_STEPS=int(os.getenv("FORGE_EDIT_STEPS", "20")),
        FORGE_CONNECT_TIMEOUT=float(os.getenv("FORGE_CONNECT_TIMEOUT", "5")),
        FORGE_READ_TIMEOUT=float(os.getenv("FORGE_READ_TIMEOUT", "300")),
    )
    if test_config:
        app.config.update(test_config)

    logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"))

    @app.before_request
    def authenticate_private_api():
        if request.path == "/health":
            return None
        supplied = request.headers.get("X-LUMA-Service-Token", "")
        if not supplied or supplied != app.config["SERVICE_TOKEN"]:
            return error_response("unauthorized", "A valid service token is required.", 401)
        return None

    @app.get("/health")
    def health():
        if is_forge_provider(app.config):
            try:
                forge_request(app.config, "GET", "/sdapi/v1/sd-models")
            except ProviderError as exc:
                return jsonify(
                    {
                        "status": "unavailable",
                        "service": "luma-ai",
                        "provider": "webui-forge",
                        "error": str(exc),
                    }
                ), 503
        return jsonify({"status": "ok", "service": "luma-ai", "provider": app.config["PROVIDER_NAME"]})

    @app.post("/v1/generate")
    def generate():
        payload = request.get_json(silent=True) or {}
        try:
            prompt = parse_prompt(payload.get("prompt"))
            width = parse_integer(payload.get("width", 512), "width", MIN_DIMENSION, MAX_DIMENSION)
            height = parse_integer(payload.get("height", 512), "height", MIN_DIMENSION, MAX_DIMENSION)
            if width % 64 or height % 64:
                raise ValueError("Width and height must be divisible by 64.")
            seed = prompt_seed(prompt, payload.get("seed"))
            negative_prompt = str(payload.get("negative_prompt", "")).strip()
            if len(negative_prompt) > MAX_PROMPT_LENGTH:
                raise ValueError("Negative prompt cannot exceed 1000 characters.")
            steps = parse_integer(payload.get("steps", 20), "steps", 1, 50)
        except ValueError as exc:
            return error_response("validation_error", str(exc), 400)

        try:
            if is_forge_provider(app.config):
                image, seed = generate_forge_image(app.config, prompt, negative_prompt, width, height, seed, steps)
            else:
                image = generate_development_image(prompt, width, height, seed)
        except ProviderUnavailable as exc:
            return error_response("provider_unavailable", str(exc), 503)
        except ProviderError as exc:
            return error_response("provider_error", str(exc), 502)
        buffer = io.BytesIO()
        image.save(buffer, format="PNG", optimize=True)
        buffer.seek(0)
        response = send_file(buffer, mimetype="image/png", download_name=f"luma-{seed}.png")
        response.headers["X-LUMA-Seed"] = str(seed)
        response.headers["X-LUMA-Provider"] = app.config["PROVIDER_NAME"]
        return response

    @app.post("/v1/edit")
    def edit():
        upload = request.files.get("image")
        if upload is None or not upload.filename:
            return error_response("validation_error", "An image file is required.", 400)
        try:
            prompt = parse_prompt(request.form.get("prompt"))
            strength = float(request.form.get("strength", "0.65"))
            if not 0 <= strength <= 1:
                raise ValueError("Strength must be between 0 and 1.")
            seed = prompt_seed(prompt, request.form.get("seed"))
            source = Image.open(upload.stream)
            source.verify()
            upload.stream.seek(0)
            source = Image.open(upload.stream)
            if source.width * source.height > MAX_DIMENSION * MAX_DIMENSION * 4:
                raise ValueError("The input image has too many pixels.")
        except (ValueError, UnidentifiedImageError) as exc:
            return error_response("validation_error", str(exc) or "The uploaded file is not a valid image.", 400)

        try:
            if is_forge_provider(app.config):
                image, seed = edit_forge_image(app.config, source, prompt, strength, seed)
            else:
                image = edit_development_image(source, prompt, strength, seed)
        except ProviderUnavailable as exc:
            return error_response("provider_unavailable", str(exc), 503)
        except ProviderError as exc:
            return error_response("provider_error", str(exc), 502)
        buffer = io.BytesIO()
        image.save(buffer, format="PNG", optimize=True)
        buffer.seek(0)
        response = send_file(buffer, mimetype="image/png", download_name=f"luma-edit-{seed}.png")
        response.headers["X-LUMA-Seed"] = str(seed)
        response.headers["X-LUMA-Provider"] = app.config["PROVIDER_NAME"]
        return response

    @app.errorhandler(413)
    def request_too_large(_error):
        return error_response("request_too_large", "The request exceeds the configured size limit.", 413)

    @app.errorhandler(404)
    def not_found(_error):
        return error_response("not_found", "The requested endpoint does not exist.", 404)

    return app


app = create_app()

if __name__ == "__main__":
    app.run(host=os.getenv("HOST", "127.0.0.1"), port=int(os.getenv("PORT", "8000")), debug=os.getenv("FLASK_DEBUG", "0") == "1")

