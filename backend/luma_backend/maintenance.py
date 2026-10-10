from __future__ import annotations

import json
import shutil
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path

from .extensions import db
from .models import Job


def ensure_outside_media(app, destination: Path) -> Path:
    media_root = Path(app.config["MEDIA_ROOT"]).resolve()
    destination = Path(destination).resolve()
    if destination == media_root or media_root in destination.parents:
        raise RuntimeError("Backup destination must be outside the media directory.")
    return destination


def sqlite_path(database_uri: str) -> Path:
    prefix = "sqlite:///"
    if not database_uri.startswith(prefix):
        raise RuntimeError("Built-in backup supports file-based SQLite only.")
    return Path(database_uri[len(prefix):]).resolve()


def backup_backend(app, destination: Path) -> Path:
    destination = ensure_outside_media(app, Path(destination))
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    backup_path = destination / f"backup-{timestamp}"
    backup_path.mkdir(parents=True, exist_ok=False)

    db_path = sqlite_path(app.config["SQLALCHEMY_DATABASE_URI"])
    backup_db = backup_path / "luma.db"
    source = sqlite3.connect(db_path)
    target = sqlite3.connect(backup_db)
    try:
        source.backup(target)
    finally:
        target.close()
        source.close()

    media_root = Path(app.config["MEDIA_ROOT"])
    media_backup = backup_path / "media"
    media_files = 0
    if media_root.exists():
        media_backup.mkdir()
        for path in media_root.rglob("*"):
            if path.is_file():
                relative = path.relative_to(media_root)
                (media_backup / relative.parent).mkdir(parents=True, exist_ok=True)
                shutil.copy2(path, media_backup / relative)
                media_files += 1

    manifest = {
        "created_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "database": "luma.db",
        "media_files": media_files,
    }
    (backup_path / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    return backup_path


def cleanup_expired_jobs(app, older_than_days: int, apply: bool = False) -> dict:
    cutoff = datetime.now(timezone.utc) - timedelta(days=older_than_days)
    result = {
        "applied": apply,
        "candidates": 0,
        "jobs_deleted": 0,
        "media_deleted": 0,
        "uploads_deleted": 0,
    }
    with app.app_context():
        jobs = db.session.scalars(
            db.select(Job).where(Job.status.in_(["completed", "failed"]), Job.updated_at < cutoff)
        ).all()
        result["candidates"] = len(jobs)
        if not apply:
            return result
        media_root = Path(app.config["MEDIA_ROOT"]).resolve()
        upload_root = Path(app.config["UPLOAD_ROOT"]).resolve()
        for job in jobs:
            if job.result_filename:
                media_path = (media_root / job.result_filename).resolve()
                if media_root in media_path.parents and media_path.exists():
                    media_path.unlink()
                    result["media_deleted"] += 1
            if job.source_filename:
                upload_path = (upload_root / job.source_filename).resolve()
                if upload_root in upload_path.parents and upload_path.exists():
                    upload_path.unlink()
                    result["uploads_deleted"] += 1
            db.session.delete(job)
            result["jobs_deleted"] += 1
        db.session.commit()
    return result
