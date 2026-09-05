from __future__ import annotations

import json
import shutil
import sqlite3
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

from flask import Flask
from sqlalchemy.engine import make_url

from .extensions import db
from .models import Job


def _managed_file(root: Path, filename: str | None) -> Path | None:
    if not filename:
        return None
    resolved_root = root.resolve()
    candidate = (resolved_root / filename).resolve()
    if resolved_root not in candidate.parents:
        raise RuntimeError("Refusing to access a file outside the configured storage root.")
    return candidate


def backup_backend(app: Flask, destination_root: Path) -> Path:
    """Create a consistent SQLite snapshot and copy the result media directory."""
    database_url = make_url(app.config["SQLALCHEMY_DATABASE_URI"])
    if not database_url.drivername.startswith("sqlite") or not database_url.database:
        raise RuntimeError("The built-in backup command supports file-based SQLite only.")

    database_path = Path(database_url.database).resolve()
    if not database_path.is_file():
        raise RuntimeError(f"SQLite database does not exist: {database_path}")

    created_at = datetime.now(timezone.utc)
    backup_name = f"luma-{created_at.strftime('%Y%m%dT%H%M%SZ')}-{uuid.uuid4().hex[:8]}"
    backup_path = destination_root.resolve() / backup_name
    media_backup = backup_path / "media"
    backup_path.mkdir(parents=True, exist_ok=False)

    source_connection = sqlite3.connect(str(database_path))
    target_connection = sqlite3.connect(str(backup_path / "luma.db"))
    try:
        with target_connection:
            source_connection.backup(target_connection)
    finally:
        target_connection.close()
        source_connection.close()

    media_root = Path(app.config["MEDIA_ROOT"]).resolve()
    if media_root.is_dir():
        shutil.copytree(media_root, media_backup)
    else:
        media_backup.mkdir()

    media_count = sum(1 for path in media_backup.rglob("*") if path.is_file())
    manifest = {
        "created_at": created_at.isoformat().replace("+00:00", "Z"),
        "database": "luma.db",
        "media_directory": "media",
        "media_files": media_count,
    }
    (backup_path / "manifest.json").write_text(
        json.dumps(manifest, indent=2), encoding="utf-8"
    )
    return backup_path


def cleanup_expired_jobs(app: Flask, older_than_days: int, apply: bool = False) -> dict[str, int | bool]:
    """Preview or remove terminal jobs and their managed files after retention expires."""
    if older_than_days < 1:
        raise ValueError("older_than_days must be at least 1")

    cutoff = datetime.now(timezone.utc) - timedelta(days=older_than_days)
    media_root = Path(app.config["MEDIA_ROOT"])
    upload_root = Path(app.config["UPLOAD_ROOT"])
    deleted_media = 0
    deleted_uploads = 0

    with app.app_context():
        jobs = db.session.scalars(
            db.select(Job).where(
                Job.status.in_(("completed", "failed")),
                Job.updated_at < cutoff,
            )
        ).all()
        if apply:
            for job in jobs:
                media_path = _managed_file(media_root, job.result_filename)
                upload_path = _managed_file(upload_root, job.source_filename)
                if media_path is not None and media_path.is_file():
                    media_path.unlink()
                    deleted_media += 1
                if upload_path is not None and upload_path.is_file():
                    upload_path.unlink()
                    deleted_uploads += 1
                db.session.delete(job)
            db.session.commit()

    return {
        "applied": apply,
        "candidates": len(jobs),
        "jobs_deleted": len(jobs) if apply else 0,
        "media_deleted": deleted_media,
        "uploads_deleted": deleted_uploads,
    }
