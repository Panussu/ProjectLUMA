# ทดสอบระบบ Live Progress Tracking และ Denoising Preview
from __future__ import annotations

import json
from luma_backend import jobs as jobs_module
from luma_backend.extensions import db
from luma_backend.models import Job, JobAIOptions


class MockResponse:
    def __init__(self, status_code: int = 200, json_data: dict | None = None):
        self.status_code = status_code
        self._json_data = json_data or {}
        self.text = json.dumps(self._json_data)

    @property
    def ok(self):
        return 200 <= self.status_code < 300

    def json(self):
        return self._json_data


def test_overall_progress_endpoint(backend_client, registered_user, monkeypatch):
    headers = {"Authorization": f"Bearer {registered_user['token']}"}

    # 1. Unauthenticated -> 401
    res = backend_client.get("/api/v1/jobs/progress")
    assert res.status_code == 401

    # 2. Authenticated live query
    calls = []

    def fake_get(url, **kwargs):
        calls.append((url, kwargs))
        return MockResponse(
            200,
            json_data={
                "status": "ok",
                "active": True,
                "progress": 0.45,
                "progress_percent": 45.0,
                "sampling_step": 9,
                "sampling_steps": 20,
                "eta_relative": 4.2,
                "preview_image": "data:image/png;base64,mockpreviewdata",
            },
        )

    monkeypatch.setattr(jobs_module.requests, "get", fake_get)

    res = backend_client.get("/api/v1/jobs/progress?include_preview=true", headers=headers)
    assert res.status_code == 200
    data = res.get_json()
    assert data["active"] is True
    assert data["progress_percent"] == 45.0
    assert data["sampling_step"] == 9
    assert data["preview_image"] == "data:image/png;base64,mockpreviewdata"

    assert len(calls) == 1
    assert calls[0][1]["params"]["include_preview"] == "true"
    assert calls[0][1]["headers"]["X-LUMA-Service-Token"] == "test-service-token"


def test_job_specific_progress_and_isolation(backend_client, backend_app, registered_user, monkeypatch):
    headers = {"Authorization": f"Bearer {registered_user['token']}"}

    with backend_app.app_context():
        queued_job = Job(
            user_id=registered_user["user"]["id"],
            type="generate",
            prompt="queued job",
            status="queued",
            progress=0,
            ai_options=JobAIOptions(request_options={}),
        )
        processing_job = Job(
            user_id=registered_user["user"]["id"],
            type="generate",
            prompt="processing job",
            status="processing",
            progress=15,
            ai_options=JobAIOptions(request_options={}),
        )
        completed_job = Job(
            user_id=registered_user["user"]["id"],
            type="generate",
            prompt="completed job",
            status="completed",
            progress=100,
            ai_options=JobAIOptions(request_options={}),
        )
        db.session.add_all([queued_job, processing_job, completed_job])
        db.session.commit()
        q_id, p_id, c_id = queued_job.id, processing_job.id, completed_job.id

    # 1. Non-existent job
    res = backend_client.get("/api/v1/jobs/non-existent-id/progress", headers=headers)
    assert res.status_code == 404

    # 2. User isolation: other user cannot see progress
    u2_res = backend_client.post(
        "/api/v1/auth/register",
        json={"username": "user2.progress", "password": "secure-password-123"},
    )
    u2_token = u2_res.get_json()["access_token"]
    u2_headers = {"Authorization": f"Bearer {u2_token}"}

    res = backend_client.get(f"/api/v1/jobs/{p_id}/progress", headers=u2_headers)
    assert res.status_code == 404

    # 3. Queued job progress
    res = backend_client.get(f"/api/v1/jobs/{q_id}/progress", headers=headers)
    assert res.status_code == 200
    assert res.get_json()["status"] == "queued"
    assert res.get_json()["progress_percent"] == 0.0

    # 4. Completed job progress
    res = backend_client.get(f"/api/v1/jobs/{c_id}/progress", headers=headers)
    assert res.status_code == 200
    assert res.get_json()["status"] == "completed"
    assert res.get_json()["progress_percent"] == 100.0

    # 5. Processing job with live preview from AI
    def fake_get(url, **kwargs):
        return MockResponse(
            200,
            json_data={
                "status": "ok",
                "active": True,
                "progress": 0.6,
                "progress_percent": 60.0,
                "sampling_step": 12,
                "sampling_steps": 20,
            },
        )

    monkeypatch.setattr(jobs_module.requests, "get", fake_get)

    res = backend_client.get(f"/api/v1/jobs/{p_id}/progress", headers=headers)
    assert res.status_code == 200
    data = res.get_json()
    assert data["job_id"] == p_id
    assert data["status"] == "processing"
    assert data["progress_percent"] == 60.0
    assert data["sampling_step"] == 12
