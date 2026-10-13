# ตัวแยกส่วนและอ่าน Metadata ข้อความการสร้างภาพ (Prompt, Negative Prompt, Settings)
"""Parser for Stable Diffusion / WebUI Forge PNG generation parameters."""

from __future__ import annotations

import re
from typing import Any


def parse_png_parameters(text: str) -> dict[str, Any]:
    """Parse Stable Diffusion WebUI / Forge / A1111 parameter text into structured dictionary."""
    if not text:
        return {}

    prompt = ""
    negative_prompt = ""
    params_line = ""

    parts = text.split("\nNegative prompt: ")
    if len(parts) == 2:
        prompt = parts[0].strip()
        rest = parts[1]
    else:
        rest = text

    steps_match = re.search(r"(?:^|\n)Steps:\s*", rest)
    if steps_match:
        if len(parts) == 2:
            negative_prompt = rest[:steps_match.start()].strip()
        else:
            prompt = rest[:steps_match.start()].strip()
        params_line = rest[steps_match.start():].strip()
    elif len(parts) == 2:
        negative_prompt = rest.strip()
    else:
        prompt = text.strip()

    parsed_params: dict[str, str] = {}
    if params_line:
        for m in re.finditer(r"([A-Za-z0-9_ ]+):\s*([^,]+)(?:,|$)", params_line):
            k = m.group(1).strip().lower().replace(" ", "_")
            v = m.group(2).strip()
            parsed_params[k] = v

    result: dict[str, Any] = {
        "prompt": prompt,
        "negative_prompt": negative_prompt,
    }

    if "steps" in parsed_params and parsed_params["steps"].isdigit():
        result["steps"] = int(parsed_params["steps"])
    if "sampler" in parsed_params:
        result["sampler"] = parsed_params["sampler"]
    if "schedule_type" in parsed_params:
        result["scheduler"] = parsed_params["schedule_type"]
    elif "scheduler" in parsed_params:
        result["scheduler"] = parsed_params["scheduler"]
    if "cfg_scale" in parsed_params:
        try:
            result["cfg_scale"] = float(parsed_params["cfg_scale"])
        except ValueError:
            pass
    if "seed" in parsed_params and parsed_params["seed"].isdigit():
        result["seed"] = int(parsed_params["seed"])
    if "size" in parsed_params and "x" in parsed_params["size"]:
        dims = parsed_params["size"].split("x")
        if len(dims) == 2 and dims[0].isdigit() and dims[1].isdigit():
            result["width"] = int(dims[0])
            result["height"] = int(dims[1])
    if "model" in parsed_params:
        result["model"] = parsed_params["model"]

    # Extract LoRA names if present in prompt
    loras = re.findall(r"<lora:([^:>]+):?([^>]*)>", prompt)
    if loras:
        result["loras"] = [name for name, _ in loras]

    return result
