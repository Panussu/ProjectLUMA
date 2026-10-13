# สแกนโมเดล LoRA และตรวจนับรายการ Samplers/Schedulers/Upscalers ในเครื่อง
"""Model & LoRA scanning and presets catalog for LUMA AI Engine."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

try:
    from .forge_client import forge_request, is_forge_provider
except (ImportError, ValueError):
    from forge_client import forge_request, is_forge_provider

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
        "category": "DPM++ High Quality",
        "description": "Clean, highly detailed textures with Karras noise schedule. Best for SDXL anime & character portraits.",
        "recommended_steps": [24, 35],
    },
    {
        "name": "DPM++ SDE Karras",
        "label": "DPM++ SDE Karras",
        "category": "DPM++ High Quality",
        "description": "Stochastic differential equation sampling. Maximum fine detail and intricate hair/clothing folds.",
        "recommended_steps": [25, 35],
    },
    {
        "name": "DPM++ 2M SDE Karras",
        "label": "DPM++ 2M SDE Karras",
        "category": "DPM++ High Quality",
        "description": "Hybrid 2M multi-step with SDE richness. Ideal for photorealistic cinematic scenes.",
        "recommended_steps": [26, 36],
    },
    {
        "name": "DDIM",
        "label": "DDIM",
        "category": "Classic Inversion",
        "description": "Fast deterministic sampling. Best suited for img2img workflows and style transfers.",
        "recommended_steps": [20, 30],
    },
    {
        "name": "UniPC",
        "label": "UniPC",
        "category": "Ultra Fast",
        "description": "Unified predictor-corrector framework. Good coherence in as few as 10-15 steps.",
        "recommended_steps": [12, 20],
    },
    {
        "name": "Heun",
        "label": "Heun",
        "category": "High Accuracy",
        "description": "Second-order Runge-Kutta solver. Sharp results, takes 2x evaluations per step.",
        "recommended_steps": [15, 25],
    },
    {
        "name": "LMS Karras",
        "label": "LMS Karras",
        "category": "Linear Multi-Step",
        "description": "Linear multi-step method with Karras schedule. Smooth gradient transitions.",
        "recommended_steps": [20, 30],
    },
]

# รายการ Scheduler มาตรฐานสำหรับกระจายระดับ Noise ในแต่ละขั้นตอน
DEFAULT_SCHEDULERS: list[dict[str, Any]] = [
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

# รายการ AI Upscaler มาตรฐานสำหรับขยายความละเอียดและเสริมรายละเอียดภาพ
DEFAULT_UPSCALERS: list[dict[str, Any]] = [
    {
        "name": "R-ESRGAN 4x+",
        "label": "R-ESRGAN 4x+ (Realistic & Universal)",
        "scale": 4,
        "description": "State of the art neural upscaler for photorealistic, cinematic, and detailed scenes.",
    },
    {
        "name": "R-ESRGAN 4x+ Anime6B",
        "label": "R-ESRGAN 4x+ Anime6B (Anime & Manga)",
        "scale": 4,
        "description": "Optimized specifically for anime illustrations, cel-shading, and clean line art.",
    },
    {
        "name": "ESRGAN_4x",
        "label": "ESRGAN 4x (Classic High Detail)",
        "scale": 4,
        "description": "Enhanced Super-Resolution GAN preserving high-frequency textures and edges.",
    },
    {
        "name": "SwinIR 4x",
        "label": "SwinIR 4x (Smooth & Denoised)",
        "scale": 4,
        "description": "Swin Transformer image restoration with clean geometry and minimal noise artifacts.",
    },
    {
        "name": "Lanczos",
        "label": "Lanczos (Fast Algorithmic)",
        "scale": 1,
        "description": "High-order sinc interpolation for fast, faithful resizing without neural hallucination.",
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
                "version": info.get("VersionName") or info.get("ModelVersion") or "v1.0",
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


# ดึงรายชื่อ AI Upscalers จาก Forge ถ้าเปิดอยู่ หรือส่งคืนรายการมาตรฐานที่เตรียมไว้
def get_supported_upscalers(config: dict[str, Any]) -> list[dict[str, Any]]:
    if is_forge_provider(config):
        try:
            resp = forge_request(config, "GET", "/sdapi/v1/upscalers")
            data = resp.json()
            if isinstance(data, list) and data:
                items = []
                for item in data:
                    name = item.get("name")
                    if name:
                        items.append({
                            "name": name,
                            "label": item.get("model_name") or name,
                            "scale": item.get("scale", 4),
                            "description": f"Forge native upscaler {name}",
                        })
                if items:
                    return items
        except Exception:
            pass
    return DEFAULT_UPSCALERS
