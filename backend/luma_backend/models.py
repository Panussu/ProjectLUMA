from __future__ import annotations

import uuid
from datetime import datetime, timezone

from werkzeug.security import check_password_hash, generate_password_hash

from .extensions import db


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(40), unique=True, nullable=False, index=True)
    password_hash = db.Column(db.String(255), nullable=False)
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utc_now)
    jobs = db.relationship("Job", back_populates="user", cascade="all, delete-orphan")

    def set_password(self, password: str) -> None:
        self.password_hash = generate_password_hash(password)

    def check_password(self, password: str) -> bool:
        return check_password_hash(self.password_hash, password)

    def to_dict(self) -> dict:
        return {"id": self.id, "username": self.username, "created_at": self.created_at.isoformat().replace("+00:00", "Z")}


class Job(db.Model):
    id = db.Column(db.String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False, index=True)
    type = db.Column(db.String(16), nullable=False)
    status = db.Column(db.String(16), nullable=False, default="queued", index=True)
    progress = db.Column(db.Integer, nullable=False, default=0)
    prompt = db.Column(db.Text, nullable=False)
    negative_prompt = db.Column(db.Text, nullable=False, default="")
    width = db.Column(db.Integer)
    height = db.Column(db.Integer)
    steps = db.Column(db.Integer)
    seed = db.Column(db.BigInteger)
    strength = db.Column(db.Float)
    source_filename = db.Column(db.String(255))
    result_filename = db.Column(db.String(255))
    provider = db.Column(db.String(80))
    error = db.Column(db.Text)
    created_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utc_now, index=True)
    updated_at = db.Column(db.DateTime(timezone=True), nullable=False, default=utc_now, onupdate=utc_now)
    completed_at = db.Column(db.DateTime(timezone=True))
    user = db.relationship("User", back_populates="jobs")

    def to_dict(self, result_url: str | None = None) -> dict:
        return {
            "id": self.id,
            "type": self.type,
            "status": self.status,
            "progress": self.progress,
            "prompt": self.prompt,
            "negative_prompt": self.negative_prompt,
            "width": self.width,
            "height": self.height,
            "steps": self.steps,
            "seed": self.seed,
            "strength": self.strength,
            "provider": self.provider,
            "created_at": self.created_at.isoformat().replace("+00:00", "Z"),
            "updated_at": self.updated_at.isoformat().replace("+00:00", "Z"),
            "completed_at": self.completed_at.isoformat().replace("+00:00", "Z") if self.completed_at else None,
            "result_url": result_url,
            "error": self.error,
        }

