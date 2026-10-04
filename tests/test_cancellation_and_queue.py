# ทดสอบการยกเลิกงาน (Cancel Job) และการจัดการคิว 429 Retry
from __future__ import annotations

import json
from luma_backend import jobs as jobs_module
from luma_backend import worker
from luma_backend.extensions import db
from luma_backend.models import Job, JobAIOptions
from luma_backend.worker import process_job


class MockResponse:
    def __init__(self, status_code: int = 200, content: bytes = b"", headers: dict | None = None, json_data: dict | None = None):
        self.status_code = status_code
        self.content = content
        self.headers = headers or {}
        self._json_data = json_data or {}
        self.text = json.dumps(self._json_data) if json_data else content.decode(errors="ignore")

    @property
    def ok(self):
        return 200 <= self.status_code < 300

    def json(self):
        return self._json_data


def test_cancel_job_endpoints_and_isolation(backend_client, backend_app, registered_user):
    headers = {"Authorization": f"Bearer {registered_user['token']}"}

    with backend_app.app_context():
        job = Job(
            user_id=registered_user["user"]["id"],
            type="generate",
            prompt="cancel me prompt",
            status="queued",
            ai_options=JobAIOptions(request_options={}),
        )
        db.session.add(job)
        db.session.commit()
        job_id = job.id

    # 1. Unauthenticated cancel
    res = backend_client.post(f"/api/v1/jobs/{job_id}/cancel")
    assert res.status_code == 401

    # 2. Cancel non-existent job
    res = backend_client.post("/api/v1/jobs/non-existent-id/cancel", headers=headers)
    assert res.status_code == 404

    # 3. User isolation: other user cannot cancel this job
    u2_res = backend_client.post(
        "/api/v1/auth/register",
        json={"username": "user2.cancel", "password": "secure-password-123"},
    )
    u2_token = u2_res.get_json()["access_token"]
    u2_headers = {"Authorization": f"Bearer {u2_token}"}

    res = backend_client.post(f"/api/v1/jobs/{job_id}/cancel", headers=u2_headers)
    assert res.status_code == 404

    # 4. Successfully cancel queued job
    res = backend_client.post(f"/api/v1/jobs/{job_id}/cancel", headers=headers)
    assert res.status_code == 200
    data = res.get_json()
    assert data["job"]["status"] == "cancelled"
    assert "cancelled" in data["job"]["error"].lower()

    # 5. Cancelling an already cancelled job returns 409
    res = backend_client.post(f"/api/v1/jobs/{job_id}/cancel", headers=headers)
    assert res.status_code == 409


def test_cancel_processing_job_sends_interrupt(backend_client, backend_app, registered_user, monkeypatch):
    headers = {"Authorization": f"Bearer {registered_user['token']}"}
    interrupt_calls = []

    def fake_post(url, **kwargs):
        interrupt_calls.append((url, kwargs))
        return MockResponse(200, json_data={"status": "interrupted"})

    monkeypatch.setattr(jobs_module.requests, "post", fake_post)

    with backend_app.app_context():
        job = Job(
            user_id=registered_user["user"]["id"],
            type="generate",
            prompt="processing cancel prompt",
            status="processing",
            ai_options=JobAIOptions(request_options={}),
        )
        db.session.add(job)
        db.session.commit()
        job_id = job.id

    res = backend_client.post(f"/api/v1/jobs/{job_id}/cancel", headers=headers)
    assert res.status_code == 200
    assert res.get_json()["job"]["status"] == "cancelled"
    assert len(interrupt_calls) == 1
    assert interrupt_calls[0][0] == "http://ai.test/v1/interrupt"
    assert interrupt_calls[0][1]["headers"]["X-LUMA-Service-Token"] == "test-service-token"


def test_worker_retries_on_429_and_captures_telemetry(backend_app, registered_user, png_bytes, monkeypatch):
    backend_app.config["AI_QUEUE_MAX_RETRIES"] = 2
    backend_app.config["AI_QUEUE_RETRY_DELAY"] = 0.01

    post_calls = []

    def fake_worker_post(url, **kwargs):
        post_calls.append((url, kwargs))
        if len(post_calls) == 1:
            return MockResponse(429, json_data={"error": {"code": "queue_full", "message": "GPU is busy"}})
        return MockResponse(
            200,
            content=png_bytes,
            headers={
                "Content-Type": "image/png",
                "X-LUMA-Seed": "9999",
                "X-LUMA-Provider": "forge",
                "X-LUMA-Queue-Wait-Ms": "45.2",
                "X-LUMA-Execution-Ms": "850.5",
                "X-LUMA-Queue-Remaining": "1",
            },
        )

    monkeypatch.setattr(worker.requests, "post", fake_worker_post)

    with backend_app.app_context():
        job = Job(
            user_id=registered_user["user"]["id"],
            type="generate",
            prompt="retry on 429 prompt",
            status="queued",
            ai_options=JobAIOptions(request_options={}),
        )
        db.session.add(job)
        db.session.commit()
        job_id = job.id

    process_job(backend_app, job_id)

    with backend_app.app_context():
        finished_job = db.session.get(Job, job_id)
        assert finished_job.status == "completed"
        assert finished_job.seed == 9999
        ai_res = finished_job.ai_options.result_options
        assert ai_res["queue_wait_ms"] == 45.2
        assert ai_res["execution_ms"] == 850.5
        assert ai_res["queue_remaining"] == 1.0
        assert len(post_calls) == 2
