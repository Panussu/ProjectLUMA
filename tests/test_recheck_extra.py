"""Target authentication bypasses and cancellation windows missed by old tests."""
import io
from pathlib import Path

import requests
from luma_backend import ai_proxy, worker
from luma_backend.extensions import db
from luma_backend.models import Job, JobAIOptions


def make_job(app, user):
    with app.app_context():
        job = Job(user_id=user['user']['id'], type='generate', prompt='audit cancellation',
                  width=256, height=256, steps=3, status='queued',
                  ai_options=JobAIOptions(request_options={}))
        db.session.add(job)
        db.session.commit()
        return job.id


def test_interrupt_requires_login_for_explicit_job(backend_app, backend_client, registered_user, monkeypatch):
    jid = make_job(backend_app, registered_user)
    monkeypatch.setattr(ai_proxy, 'forward_ai_request', lambda *a, **k: ({'status': 'ok'}, 200))
    response = backend_client.post('/api/v1/interrupt', json={'job_id': jid})
    assert response.status_code == 401


def test_invalid_jwt_cannot_reach_gpu_controls(backend_app, backend_client, registered_user, monkeypatch):
    jid = make_job(backend_app, registered_user)
    monkeypatch.setattr(ai_proxy, 'forward_ai_request', lambda *a, **k: ({'status': 'ok'}, 200))
    response = backend_client.post('/api/v1/interrupt', json={'job_id': jid}, headers={'Authorization': 'Bearer invalid'})
    assert response.status_code == 401


def test_skip_checks_job_ownership(backend_app, backend_client, registered_user, monkeypatch):
    jid = make_job(backend_app, registered_user)
    another = backend_client.post('/api/v1/auth/register', json={'username': 'audit.other', 'password': 'test-fixture-password'}).get_json()
    monkeypatch.setattr(ai_proxy, 'forward_ai_request', lambda *a, **k: ({'status': 'ok'}, 200))
    response = backend_client.post('/api/v1/skip', json={'job_id': jid}, headers={'Authorization': 'Bearer '+another['access_token']})
    assert response.status_code in {403, 404}


def test_late_cancellation_is_not_overwritten(backend_app, registered_user, png_bytes, monkeypatch):
    jid = make_job(backend_app, registered_user)
    class Reply:
        ok = True
        status_code = 200
        content = png_bytes
        headers = {'Content-Type': 'image/png'}
    monkeypatch.setattr(worker.requests, 'post', lambda *a, **k: Reply())
    original = worker.persist_ai_result
    def cancel_after_last_check(job, headers):
        with backend_app.app_context():
            other = db.session.get(Job, jid)
            other.status = 'cancelled'
            db.session.commit()
        original(job, headers)
    monkeypatch.setattr(worker, 'persist_ai_result', cancel_after_last_check)
    worker.process_job(backend_app, jid)
    with backend_app.app_context():
        assert db.session.get(Job, jid).status == 'cancelled'
        assert not (Path(backend_app.config['MEDIA_ROOT']) / (jid+'.png')).exists()


def test_timeout_preserves_cancellation(backend_app, registered_user, monkeypatch):
    jid = make_job(backend_app, registered_user)
    def cancel_then_timeout(*args, **kwargs):
        with backend_app.app_context():
            other = db.session.get(Job, jid)
            other.status = 'cancelled'
            db.session.commit()
        raise requests.Timeout('audit fixture timeout')
    monkeypatch.setattr(worker.requests, 'post', cancel_then_timeout)
    worker.process_job(backend_app, jid)
    with backend_app.app_context():
        assert db.session.get(Job, jid).status == 'cancelled'
