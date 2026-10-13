# ชุด Style Presets และระบบปรับแต่ง Prompt อัตโนมัติ (LUMA AI Engine)
"""Curated Style Presets and prompt enhancement algorithms for LUMA AI Engine."""

from __future__ import annotations

from typing import Any

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
