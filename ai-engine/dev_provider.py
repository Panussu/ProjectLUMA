# ระบบสร้างและแปลงภาพจำลองสำหรับโหมด Development / Procedural (LUMA AI Engine)
"""Development procedural provider implementation for LUMA AI Engine."""

from __future__ import annotations

import base64
import io
import random
import textwrap
import time
from typing import Any

from PIL import Image, ImageChops, ImageDraw, ImageEnhance, ImageFilter, ImageFont, ImageOps

try:
    from .forge_client import forge_request, is_forge_provider
    from .queue_manager import GenerationQueueManager
    from .validators import MAX_DIMENSION
except (ImportError, ValueError):
    from forge_client import forge_request, is_forge_provider
    from queue_manager import GenerationQueueManager
    from validators import MAX_DIMENSION


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


# วิเคราะห์ภาพจำลองโดยประเมินสี สัดส่วน และความสว่าง เพื่อสร้างแท็ก DeepDanbooru หรือคำบรรยาย
def interrogate_development_image(source: Image.Image, model: str = "deepdanbooru") -> str:
    image = ImageOps.exif_transpose(source).convert("RGB")
    thumb = image.resize((16, 16), Image.Resampling.BILINEAR)
    pixels = list(thumb.getdata())
    avg_r = sum(p[0] for p in pixels) / len(pixels)
    avg_g = sum(p[1] for p in pixels) / len(pixels)
    avg_b = sum(p[2] for p in pixels) / len(pixels)
    brightness = (avg_r * 299 + avg_g * 587 + avg_b * 114) / 1000

    aspect_ratio = image.width / max(1, image.height)
    tags: list[str] = []

    # Aspect ratio / composition
    if aspect_ratio < 0.85:
        tags.extend(["1girl", "solo", "portrait", "upper_body"])
    elif aspect_ratio > 1.25:
        tags.extend(["scenery", "landscape", "outdoors", "wide_shot"])
    else:
        tags.extend(["1girl", "solo", "close_up"])

    # Brightness / atmosphere
    if brightness > 150:
        tags.extend(["bright", "day", "sunlight"])
    elif brightness < 80:
        tags.extend(["dark", "night", "glowing", "dramatic_lighting"])
    else:
        tags.extend(["soft_lighting", "ambient_light"])

    # Dominant tones
    if avg_b > avg_r + 20 and avg_b > avg_g + 10:
        tags.extend(["blue_theme", "blue_eyes", "sky"])
    elif avg_r > avg_b + 20 and avg_r > avg_g + 10:
        tags.extend(["warm_colors", "sunset", "red_hair"])
    elif avg_g > avg_r + 15 and avg_g > avg_b + 15:
        tags.extend(["nature", "greenery", "forest"])

    # Quality & stylization tags
    tags.extend(["looking_at_viewer", "smile", "highly_detailed", "masterpiece", "best_quality"])

    if str(model).lower() == "clip":
        subject = "1girl" if "1girl" in tags else "a scenic landscape"
        lighting = "bright daylight" if brightness > 120 else "dramatic night lighting"
        return f"a masterpiece digital artwork of {subject}, {lighting}, vibrant color palette, highly detailed background"

    # Default to DeepDanbooru comma-separated tags
    return ", ".join(tags)


# ขยายขนาดภาพจำลองด้วย Pillow Lanczos พร้อมปรับปรุงความคมชัดระดับไมโครสำหรับโหมดทดสอบ
def upscale_development_image(
    source: Image.Image,
    scale_factor: float = 2.0,
    upscaler: str = "Lanczos",
) -> Image.Image:
    image = ImageOps.exif_transpose(source).convert("RGB")
    new_w = max(64, int(image.width * float(scale_factor)))
    new_h = max(64, int(image.height * float(scale_factor)))

    # 1. High-order Lanczos interpolation
    upscaled = image.resize((new_w, new_h), Image.Resampling.LANCZOS)

    # 2. Subtle micro-contrast and edge enhancement
    sharpened = ImageEnhance.Sharpness(upscaled).enhance(1.25)
    detailed = sharpened.filter(ImageFilter.DETAIL)
    return detailed


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
