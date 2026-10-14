from __future__ import annotations

import io
from collections import Counter

import requests
from PIL import Image, ImageFilter, ImageOps


FILTERS = [
    {"id": "grayscale", "name": "Grayscale"},
    {"id": "edge", "name": "Edge Detection"},
    {"id": "blur", "name": "Gaussian Blur"},
    {"id": "invert", "name": "Invert"},
]

UPSCALERS = [
    {"id": "Lanczos", "name": "Lanczos"},
    {"id": "Nearest", "name": "Nearest"},
    {"id": "Bicubic", "name": "Bicubic"},
]


def png_bytes(image: Image.Image) -> bytes:
    output = io.BytesIO()
    image.save(output, format="PNG")
    return output.getvalue()


def open_image(stream) -> Image.Image:
    image = Image.open(stream)
    if image.width * image.height > 4_194_304:
        raise ValueError("The input image has too many pixels.")
    image.load()
    return image.convert("RGB")


def apply_filter(image: Image.Image, operation: str) -> Image.Image:
    rgb = image.convert("RGB")
    if operation == "grayscale":
        return ImageOps.grayscale(rgb).convert("RGB")
    if operation == "edge":
        gray = ImageOps.grayscale(rgb)
        edges = gray.filter(ImageFilter.FIND_EDGES)
        return ImageOps.invert(edges).convert("RGB")
    if operation == "blur":
        return rgb.filter(ImageFilter.GaussianBlur(radius=4))
    if operation == "invert":
        return ImageOps.invert(rgb)
    raise ValueError("Unsupported filter operation.")


def upscale(image: Image.Image, scale_factor: float, upscaler: str = "Lanczos") -> tuple[Image.Image, str]:
    if scale_factor not in {2.0, 3.0, 4.0}:
        raise ValueError("scale_factor must be 2.0, 3.0, or 4.0.")
    if image.width * scale_factor > 4096 or image.height * scale_factor > 4096:
        raise ValueError("Upscaled dimensions cannot exceed 4096 pixels.")
    width = int(image.width * scale_factor)
    height = int(image.height * scale_factor)
    resample_map = {
        "Lanczos": Image.Resampling.LANCZOS,
        "Nearest": Image.Resampling.NEAREST,
        "Bicubic": Image.Resampling.BICUBIC,
        "Bilinear": Image.Resampling.BILINEAR,
    }
    mode = resample_map.get(upscaler, Image.Resampling.LANCZOS)
    used = upscaler if upscaler in resample_map else "Lanczos"
    return image.resize((width, height), mode), used


def procedural_interrogate(image: Image.Image, model: str) -> dict:
    small = image.convert("RGB").resize((1, 1))
    r, g, b = small.getpixel((0, 0))
    color = "red" if r >= g and r >= b else "green" if g >= r and g >= b else "blue"
    width, height = image.size
    orientation = "square" if width == height else "landscape" if width > height else "portrait"
    tags = [orientation, f"{color}_tone", "image"]
    counts = Counter(tags)
    caption = ", ".join(counts.keys())
    return {
        "status": "ok",
        "model": model,
        "caption": caption,
        "tags": list(counts.keys()),
        "provider": "backend-procedural-interrogate",
    }
