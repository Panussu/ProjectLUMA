from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path

from luma_backend.extensions import db
from luma_backend.maintenance import backup_backend, cleanup_expired_jobs
from luma_backend.models import Job, User


def persisted_completed_job(backend_app, age_days: int = 0) -> tuple[str, Path]:
    media_path = Path(backend_app.config["MEDIA_ROOT"]) / "completed.png"
    media_path.write_bytes(b"stored-result")
    with backend_app.app_context():
        user = User(username=f"retention-user-{age_days}")
        user.set_password("correct-horse-battery")
        db.session.add(user)
        db.session.flush()
        job = Job(
            user_id=user.id,
            type="generate",
            status="completed",
            prompt="stored result",
            result_filename=media_path.name,
            updated_at=datetime.now(timezone.utc) - timedelta(days=age_days),
        )
        db.session.add(job)
        db.session.commit()
        job_id = job.id
    return job_id, media_path


def test_backup_contains_database_media_and_manifest(backend_app, tmp_path):
    persisted_completed_job(backend_app)

    backup_path = backup_backend(backend_app, tmp_path / "backups")

    assert (backup_path / "luma.db").is_file()
    assert (backup_path / "media" / "completed.png").read_bytes() == b"stored-result"
    manifest = json.loads((backup_path / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["media_files"] == 1
    connection = sqlite3.connect(backup_path / "luma.db")
    try:
        assert connection.execute("SELECT COUNT(*) FROM job").fetchone()[0] == 1
    finally:
        connection.close()


def test_cleanup_previews_before_deleting_expired_jobs(backend_app):
    job_id, media_path = persisted_completed_job(backend_app, age_days=31)

    preview = cleanup_expired_jobs(backend_app, older_than_days=30)
    assert preview == {
        "applied": False,
        "candidates": 1,
        "jobs_deleted": 0,
        "media_deleted": 0,
        "uploads_deleted": 0,
    }
    assert media_path.is_file()

    result = cleanup_expired_jobs(backend_app, older_than_days=30, apply=True)
    assert result["jobs_deleted"] == 1
    assert result["media_deleted"] == 1
    assert not media_path.exists()
    with backend_app.app_context():
        assert db.session.get(Job, job_id) is None
