"""ทดสอบการแยกงานและการยกเลิกโดยไม่ต้องใช้ GPU จริง"""
import importlib.util
import io
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from PIL import Image


@pytest.fixture
def scoped_ai_module():
    spec = importlib.util.spec_from_file_location("luma_scoped_ai", Path(__file__).parents[1] / "ai-engine" / "app.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_progress_and_interrupt_only_target_active_job(scoped_ai_module, monkeypatch):
    module = scoped_ai_module
    app = module.create_app({"SERVICE_TOKEN": "test-service-token", "PROVIDER_NAME": "forge", "MAX_CONCURRENT_GENERATIONS": 4})
    queue = app.state.queue
    assert queue.max_concurrency == 1
    calls = []
    monkeypatch.setattr(module, "forge_request", lambda *args, **kwargs: calls.append(args))
    monkeypatch.setattr(module, "get_live_progress", lambda *args, **kwargs: {"preview_image": "own-image", "active": True})
    headers = {"X-LUMA-Service-Token": "test-service-token"}
    with TestClient(app) as client, queue.acquire(job_id="owner-a"):
        assert client.post("/v1/interrupt", headers=headers).status_code == 400
        preview = client.get("/v1/progress?job_id=owner-b&include_preview=true", headers=headers).json()
        assert preview["active"] is False
        assert preview["preview_image"] is None
        assert client.post("/v1/interrupt?job_id=owner-b", headers=headers).json()["status"] == "cancelled"
        assert client.post("/v1/skip?job_id=owner-b", headers=headers).status_code == 409
        assert calls == []
        preview = client.get("/v1/progress?job_id=owner-a&include_preview=true", headers=headers).json()
        assert preview["job_id"] == "owner-a"
        assert preview["preview_image"] == "own-image"
        assert client.post("/v1/interrupt?job_id=owner-a", headers=headers).status_code == 200
        assert len(calls) == 1
        assert calls[0][2] == "/sdapi/v1/interrupt"
    with pytest.raises(module.ApiError, match="cancelled"):
        with queue.acquire(job_id="owner-b"):
            pytest.fail("A cancelled job must not start")
    assert queue.active_jobs == queue.queued_jobs == 0


def test_generation_and_edit_register_backend_job_id(scoped_ai_module, monkeypatch):
    from contextlib import contextmanager
    module = scoped_ai_module
    app = module.create_app({"SERVICE_TOKEN": "test-service-token", "PROVIDER_NAME": "development-procedural"})
    queue = app.state.queue
    original = queue.acquire
    seen = []

    @contextmanager
    def tracking_acquire(*args, **kwargs):
        seen.append(kwargs.get("job_id"))
        with original(*args, **kwargs) as stats:
            yield stats

    monkeypatch.setattr(queue, "acquire", tracking_acquire)
    headers = {"X-LUMA-Service-Token": "test-service-token", "X-LUMA-Job-ID": "backend-job"}
    image = io.BytesIO()
    Image.new("RGB", (64, 64)).save(image, format="PNG")
    with TestClient(app) as client:
        result = client.post("/v1/generate", json={"prompt": "test image", "width": 256, "height": 256}, headers=headers)
        assert result.status_code == 200, result.text
        result = client.post("/v1/edit", data={"prompt": "test edit"}, files={"image": ("test.png", image.getvalue(), "image/png")}, headers=headers)
        assert result.status_code == 200, result.text
    assert seen == ["backend-job", "backend-job"]


def test_cancellation_while_waiting_releases_queue_slot(scoped_ai_module):
    import threading
    import time
    module = scoped_ai_module
    queue = module.GenerationQueueManager()
    result = []

    def waiting_job():
        try:
            with queue.acquire(job_id="waiting", timeout=2):
                result.append("ran")
        except module.ApiError as error:
            result.append(error.code)

    with queue.acquire(job_id="active"):
        thread = threading.Thread(target=waiting_job)
        thread.start()
        deadline = time.monotonic() + 1
        while queue.queued_jobs != 1 and time.monotonic() < deadline:
            time.sleep(0.005)
        assert queue.queued_jobs == 1
        with queue._lock:
            queue._cancelled_job_ids["waiting"] = time.monotonic()
    thread.join(timeout=3)
    assert not thread.is_alive()
    assert result == ["job_cancelled"]
    assert queue.active_jobs == queue.queued_jobs == 0
