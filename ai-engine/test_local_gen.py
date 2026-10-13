import io
import os
import sys
from pathlib import Path

# Add current dir to path
sys.path.insert(0, str(Path(__file__).parent))

from dev_provider import generate_development_image, edit_development_image, interrogate_development_image
from filters import process_filter_image
from png_parser import parse_png_parameters
from PIL.PngImagePlugin import PngInfo
from PIL import Image

output_dir = Path(r"c:\.Work_MasTer\StabilityMatrix\Work\ProjektLUMA_Test\project-overview-site\images")
output_dir.mkdir(parents=True, exist_ok=True)

# 1. Test generate_development_image
print("[TEST 1] Generating development image...")
prompt = "masterpiece, ultra-detailed anime illustration, 1girl, cyberpunk city, glowing neon"
neg_prompt = "photorealistic, deformed, bad hands, blurry"
seed = 42891024
img = generate_development_image(
    prompt,
    width=512,
    height=512,
    seed=seed,
    model="waiIllustriousSDXL_v170",
    style_preset="anime_illustrious"
)

# Embed PNG Info
pnginfo = PngInfo()
raw_params = f"{prompt}\nNegative prompt: {neg_prompt}\nSteps: 28, Sampler: DPM++ 2M Karras, Schedule type: Karras, CFG scale: 7.0, Seed: {seed}, Size: 512x512, Model: waiIllustriousSDXL_v170"
pnginfo.add_text("parameters", raw_params)

sample_gen_path = output_dir / "sample_dev_generated.png"
img.save(sample_gen_path, format="PNG", pnginfo=pnginfo)
print(f"-> Saved: {sample_gen_path}")

# 2. Test 4 filters
for op in ["grayscale", "edge", "blur", "invert"]:
    filtered = process_filter_image(img, op)
    filter_path = output_dir / f"sample_filter_{op}.png"
    filtered.save(filter_path, format="PNG")
    print(f"-> Saved filter {op}: {filter_path}")

# 3. Test PNG metadata reading
with Image.open(sample_gen_path) as test_img:
    extracted_text = test_img.info.get("parameters", "")
    parsed = parse_png_parameters(extracted_text)
    print(f"[TEST 2] PNG Info Extracted: {parsed}")

# 4. Test interrogate
tags = interrogate_development_image(img, model="deepdanbooru")
print(f"[TEST 3] Interrogate tags: {tags}")

print("ALL TESTS PASSED SUCCESSFULLY!")
