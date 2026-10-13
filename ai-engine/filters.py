# ระบบประมวลผลฟิลเตอร์ภาพตามมาตรฐาน API_Workshop (LUMA AI Engine)
"""Image Filter and Processing algorithms (API_Workshop compatible)."""

from __future__ import annotations

from PIL import Image, ImageFilter, ImageOps

FILTER_OPERATIONS = {"grayscale", "edge", "blur", "invert"}
ALLOWED_FILTER_CONTENT_TYPES = {"image/jpeg", "image/png", "image/webp"}


# ประมวลผลภาพตาม operation ที่เลือก (Grayscale, Edge Detection, Blur, Invert)
def process_filter_image(image: Image.Image, operation: str) -> Image.Image:
    """ประมวลผลภาพตาม operation ที่เลือก แล้วคืน Pillow Image โหมด RGB (API_Workshop compatible)."""
    # ทำให้ทุก operation รับข้อมูลสีสาม channel เหมือนกัน
    rgb_image = image.convert("RGB")

    # Algorithm 1: Grayscale - Luminance Weighted Sum Algorithm (ITU-R BT.601)
    # Y = 0.299*R + 0.587*G + 0.114*B
    if operation == "grayscale":
        return ImageOps.grayscale(rgb_image).convert("RGB")

    # Algorithm: Gaussian Blur - 2D Gaussian Spatial Kernel Convolution Filter
    if operation == "blur":
        return rgb_image.filter(ImageFilter.GaussianBlur(radius=4))

    # Algorithm 2: Edge Detection - 2D Spatial Convolution Filter (Laplacian / FIND_EDGES with White Background & Black Lines)
    if operation == "edge":
        gray = ImageOps.grayscale(rgb_image)
        edges = gray.filter(ImageFilter.FIND_EDGES)
        return ImageOps.invert(edges).convert("RGB")

    # Algorithm: Invert - Arithmetic Channel Inversion (255 - x)
    if operation == "invert":
        return ImageOps.invert(rgb_image)

    raise ValueError(f"Unsupported operation: {operation}")
