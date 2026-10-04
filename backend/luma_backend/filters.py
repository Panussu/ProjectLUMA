# รองรับ 5 อัลกอริทึมการประมวลผลภาพ (5 Distinct Image Processing & Super-Resolution Algorithms)
from __future__ import annotations

import io
import math
from typing import Tuple

import requests
from flask import Blueprint, Response, current_app, jsonify, request
from PIL import Image, ImageFilter, ImageOps, UnidentifiedImageError

from .jobs import error_response

filters_blueprint = Blueprint("filters", __name__)
ALLOWED_OPERATIONS = {"grayscale", "edge", "blur", "invert"}
ALLOWED_FORMATS = {"PNG", "JPEG", "WEBP"}


def process_local_filter(image: Image.Image, operation: str) -> Image.Image:
    """ประมวลผลภาพด้วย 4 อัลกอริทึมพื้นฐาน (ITU-R BT.601, Laplacian Edge, Gaussian Blur, Color Invert)."""
    rgb = image.convert("RGB")
    if operation == "grayscale":
        # Algorithm 1: Grayscale Luminance Transform (ITU-R BT.601: 0.299R + 0.587G + 0.114B)
        return ImageOps.grayscale(rgb).convert("RGB")
    elif operation == "edge":
        # Algorithm 2: Edge Detection 2D Spatial Convolution (Laplacian 3x3 Gradient Kernel / FIND_EDGES)
        return rgb.filter(ImageFilter.FIND_EDGES)
    elif operation == "blur":
        # Algorithm 3: Gaussian Blur 2D Spatial Kernel Smoothing (radius=4)
        return rgb.filter(ImageFilter.GaussianBlur(radius=4))
    elif operation == "invert":
        # Algorithm 4: Color Inversion Arithmetic Negation (I_out = 255 - I_in)
        return ImageOps.invert(rgb)
    raise ValueError(f"Unsupported operation: {operation}")


def upscale_local_image(image: Image.Image, scale_factor: float) -> Image.Image:
    """Algorithm 5: Image Super-Resolution via Lanczos Windowed Sinc Resampling (L(x) = sinc(x)*sinc(x/a))."""
    new_w = max(16, int(round(image.width * scale_factor)))
    new_h = max(16, int(round(image.height * scale_factor)))
    return image.resize((new_w, new_h), resample=Image.Resampling.LANCZOS)


def extract_uploaded_image():
    upload = request.files.get("file") or request.files.get("image")
    if not upload or not upload.filename:
        return None, None, None, error_response("validation_error", "An image file is required (file or image).", 400)

    try:
        content = upload.read()
        if not content:
            return None, None, None, error_response("validation_error", "Uploaded image file is empty.", 400)
        with Image.open(io.BytesIO(content)) as img:
            img.verify()
            fmt = img.format
            if fmt not in ALLOWED_FORMATS:
                return None, None, None, error_response("validation_error", "Only PNG, JPEG, and WebP images are accepted.", 400)
        with Image.open(io.BytesIO(content)) as img:
            img.load()
            if img.width * img.height > current_app.config["MAX_OUTPUT_PIXELS"]:
                return None, None, None, error_response("validation_error", "Input image exceeds maximum allowed pixel count.", 400)
            return content, fmt, img, None
    except (UnidentifiedImageError, OSError, ValueError) as exc:
        return None, None, None, error_response("validation_error", f"Invalid image file: {exc}", 400)


@filters_blueprint.get("/filters")
def get_filters():
    """List 4 supported image filter algorithms."""
    return jsonify(
        {
            "operations": [
                {
                    "id": "grayscale",
                    "name": "Grayscale Luminance Transform",
                    "algorithm": "ITU-R BT.601 Weighted Sum (0.299*R + 0.587*G + 0.114*B)",
                    "complexity": "O(W x H)",
                },
                {
                    "id": "edge",
                    "name": "Edge Detection 2D Spatial Convolution",
                    "algorithm": "Laplacian / FIND_EDGES 3x3 Gradient Magnitude",
                    "complexity": "O(W x H x K^2)",
                },
                {
                    "id": "blur",
                    "name": "Gaussian Blur Smoothing",
                    "algorithm": "2D Gaussian Spatial Kernel Convolution Filter (radius=4)",
                    "complexity": "O(W x H x r)",
                },
                {
                    "id": "invert",
                    "name": "Color Inversion Complement",
                    "algorithm": "Pointwise Arithmetic Channel Negation (255 - X)",
                    "complexity": "O(W x H)",
                },
            ],
            "default": "grayscale",
        }
    )


@filters_blueprint.get("/upscalers")
def get_upscalers():
    """List supported image super-resolution upscalers."""
    return jsonify(
        {
            "upscalers": [
                {
                    "id": "Lanczos",
                    "name": "Lanczos Windowed Sinc Resampling",
                    "description": "High-quality 8-lobe windowed sinc anti-aliasing interpolation",
                    "scale_factors": [1.5, 2.0, 3.0, 4.0],
                },
                {
                    "id": "R-ESRGAN 4x+ Anime6B",
                    "name": "Real-ESRGAN Anime 6B",
                    "description": "Deep Residual-in-Residual Dense Network optimized for anime illustrations",
                    "scale_factors": [2.0, 4.0],
                },
                {
                    "id": "R-ESRGAN 4x+",
                    "name": "Real-ESRGAN 4x+ General",
                    "description": "Photorealistic deep neural network super-resolution",
                    "scale_factors": [2.0, 4.0],
                },
            ],
            "default": "Lanczos",
        }
    )


@filters_blueprint.post("/process")
def process_filter():
    """Execute one of the 4 image filter algorithms (grayscale, edge, blur, invert)."""
    raw_op = request.form.get("operation") or request.args.get("operation") or "grayscale"
    operation = str(raw_op).strip().lower()
    if operation not in ALLOWED_OPERATIONS:
        return error_response(
            "validation_error",
            f"Unsupported operation '{operation}'. Supported: {', '.join(sorted(ALLOWED_OPERATIONS))}",
            400,
        )

    content, fmt, image, err = extract_uploaded_image()
    if err:
        return err

    # Try upstream AiEngine first if configured
    ai_url = f"{current_app.config['AI_SERVICE_URL'].rstrip('/')}/v1/process"
    headers = {"X-LUMA-Service-Token": current_app.config["AI_SERVICE_TOKEN"]}
    timeout = (current_app.config["AI_CONNECT_TIMEOUT"], current_app.config["AI_READ_TIMEOUT"])

    try:
        upstream_resp = requests.post(
            ai_url,
            data={"operation": operation},
            files={"file": (f"input.{fmt.lower()}", content, f"image/{fmt.lower()}")},
            headers=headers,
            timeout=timeout,
            allow_redirects=False,
        )
        if upstream_resp.status_code == 200 and upstream_resp.content:
            return Response(
                upstream_resp.content,
                mimetype="image/png",
                headers={
                    "Content-Disposition": f'inline; filename="processed-{operation}.png"',
                    "X-Image-Operation": operation,
                    "X-LUMA-Operation": operation,
                    "X-LUMA-Provider": upstream_resp.headers.get("X-LUMA-Provider", "ai-engine"),
                },
            )
    except requests.RequestException:
        current_app.logger.warning("Upstream AiEngine process endpoint unreachable; falling back to local algorithm")

    # Local High-Fidelity Algorithm Processing
    result_img = process_local_filter(image, operation)
    buf = io.BytesIO()
    result_img.save(buf, format="PNG")
    output_bytes = buf.getvalue()

    return Response(
        output_bytes,
        mimetype="image/png",
        headers={
            "Content-Disposition": f'inline; filename="processed-{operation}.png"',
            "X-Image-Operation": operation,
            "X-LUMA-Operation": operation,
            "X-LUMA-Provider": "backend-procedural",
            "X-LUMA-Width": str(result_img.width),
            "X-LUMA-Height": str(result_img.height),
        },
    )


@filters_blueprint.post("/upscale")
def upscale_image():
    """Execute Algorithm 5: Super-Resolution & Lanczos Windowed Sinc Resampling."""
    raw_scale = request.form.get("scale_factor") or request.args.get("scale_factor") or "2.0"
    try:
        scale_factor = float(raw_scale)
        if not (1.0 <= scale_factor <= 4.0 and math.isfinite(scale_factor)):
            raise ValueError()
    except (TypeError, ValueError):
        return error_response("validation_error", "scale_factor must be a number between 1.0 and 4.0.", 400)

    upscaler = (request.form.get("upscaler") or request.args.get("upscaler") or "Lanczos").strip()

    content, fmt, image, err = extract_uploaded_image()
    if err:
        return err

    # Try upstream AiEngine first
    ai_url = f"{current_app.config['AI_SERVICE_URL'].rstrip('/')}/v1/upscale"
    headers = {"X-LUMA-Service-Token": current_app.config["AI_SERVICE_TOKEN"]}
    timeout = (current_app.config["AI_CONNECT_TIMEOUT"], current_app.config["AI_READ_TIMEOUT"])

    try:
        upstream_resp = requests.post(
            ai_url,
            data={"scale_factor": str(scale_factor), "upscaler": upscaler},
            files={"image": (f"input.{fmt.lower()}", content, f"image/{fmt.lower()}")},
            headers=headers,
            timeout=timeout,
            allow_redirects=False,
        )
        if upstream_resp.status_code == 200 and upstream_resp.content:
            return Response(
                upstream_resp.content,
                mimetype="image/png",
                headers={
                    "Content-Disposition": 'inline; filename="upscaled.png"',
                    "X-LUMA-Upscaler": upscaler,
                    "X-LUMA-Scale-Factor": str(scale_factor),
                    "X-LUMA-Provider": upstream_resp.headers.get("X-LUMA-Provider", "ai-engine"),
                },
            )
    except requests.RequestException:
        current_app.logger.warning("Upstream AiEngine upscale endpoint unreachable; falling back to local Lanczos")

    # Local Lanczos Sinc Resampling
    upscaled = upscale_local_image(image, scale_factor)
    buf = io.BytesIO()
    upscaled.save(buf, format="PNG")
    output_bytes = buf.getvalue()

    return Response(
        output_bytes,
        mimetype="image/png",
        headers={
            "Content-Disposition": 'inline; filename="upscaled.png"',
            "X-LUMA-Upscaler": "Lanczos",
            "X-LUMA-Scale-Factor": str(scale_factor),
            "X-LUMA-Provider": "backend-lanczos",
            "X-LUMA-Width": str(upscaled.width),
            "X-LUMA-Height": str(upscaled.height),
        },
    )
