# ทดสอบ 5 อัลกอริทึมการประมวลผลภาพ (Grayscale, Edge, Blur, Invert, Lanczos Upscale)
from __future__ import annotations

import io
from PIL import Image


def test_filters_and_upscalers_discovery(backend_client):
    # 1. Discover filters
    res = backend_client.get("/api/v1/filters")
    assert res.status_code == 200
    ops = res.get_json()["operations"]
    op_ids = {op["id"] for op in ops}
    assert op_ids == {"grayscale", "edge", "blur", "invert"}

    # 2. Discover upscalers
    res = backend_client.get("/api/v1/upscalers")
    assert res.status_code == 200
    upscalers = res.get_json()["upscalers"]
    assert any(u["id"] == "Lanczos" for u in upscalers)


def test_process_filter_algorithms(backend_client, png_bytes):
    # 1. Missing image file
    res = backend_client.post("/api/v1/process", data={"operation": "grayscale"})
    assert res.status_code == 400

    # 2. Invalid operation
    res = backend_client.post(
        "/api/v1/process",
        data={"file": (io.BytesIO(png_bytes), "test.png"), "operation": "unknown_op"},
    )
    assert res.status_code == 400

    # 3. Test each of the 4 filter algorithms
    for op in ("grayscale", "edge", "blur", "invert"):
        res = backend_client.post(
            "/api/v1/process",
            data={"file": (io.BytesIO(png_bytes), "test.png"), "operation": op},
        )
        assert res.status_code == 200
        assert res.headers["Content-Type"] == "image/png"
        assert res.headers["X-Image-Operation"] == op

        with Image.open(io.BytesIO(res.data)) as result_img:
            result_img.verify()
            assert result_img.format == "PNG"
            assert result_img.size == (64, 64)


def test_upscale_algorithm(backend_client, png_bytes):
    # 1. Invalid scale factor
    res = backend_client.post(
        "/api/v1/upscale",
        data={"file": (io.BytesIO(png_bytes), "test.png"), "scale_factor": "5.0"},
    )
    assert res.status_code == 400

    # 2. Valid 2x Upscale via Lanczos Sinc Resampling
    res = backend_client.post(
        "/api/v1/upscale",
        data={"file": (io.BytesIO(png_bytes), "test.png"), "scale_factor": "2.0"},
    )
    assert res.status_code == 200
    assert res.headers["Content-Type"] == "image/png"
    assert res.headers["X-LUMA-Scale-Factor"] == "2.0"

    with Image.open(io.BytesIO(res.data)) as result_img:
        result_img.verify()
        assert result_img.format == "PNG"
        assert result_img.size == (128, 128)  # 64 * 2 = 128
