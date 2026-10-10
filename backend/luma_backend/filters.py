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
    image.load()
    return image.convert("RGB")


def apply_filter(image: Image.Image, operation: str) -> Image.Image:
    if operation == "grayscale":
        return ImageOps.grayscale(image).convert("RGB")
    if operation == "edge":
        return ImageOps.grayscale(image).filter(ImageFilter.FIND_EDGES).convert("RGB")
    if operation == "blur":
        return image.filter(ImageFilter.GaussianBlur(radius=2))
    if operation == "invert":
        return ImageOps.invert(image.convert("RGB"))
    raise ValueError("Unsupported filter operation.")


def upscale(image: Image.Image, scale_factor: float) -> Image.Image:
    if scale_factor not in {2.0, 3.0, 4.0}:
        raise ValueError("scale_factor must be 2.0, 3.0, or 4.0.")
    width = int(image.width * scale_factor)
    height = int(image.height * scale_factor)
    return image.resize((width, height), Image.Resampling.LANCZOS)


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
