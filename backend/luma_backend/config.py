from __future__ import annotations

import os
from datetime import timedelta
from pathlib import Path
from typing import Any, Mapping
from urllib.parse import urlparse


PROTECTED_DEPLOYMENT_MODES = {"vlan", "production"}


def _is_placeholder_secret(value: str) -> bool:
    normalized = value.strip().casefold()
    return not normalized or "change-me" in normalized or normalized.startswith("replace-with")


def validate_runtime_config(config: Mapping[str, Any]) -> None:
    """Reject unsafe or incomplete settings before a LAN-facing server starts."""
    mode = str(config.get("DEPLOYMENT_MODE", "development")).strip().casefold()
    if mode not in PROTECTED_DEPLOYMENT_MODES:
        return

    errors: list[str] = []
    secrets = {
        "SECRET_KEY": str(config.get("SECRET_KEY", "")),
        "JWT_SECRET_KEY": str(config.get("JWT_SECRET_KEY", "")),
        "AI_SERVICE_TOKEN": str(config.get("AI_SERVICE_TOKEN", "")),
    }
    for name, value in secrets.items():
        if _is_placeholder_secret(value) or len(value) < 32:
            errors.append(f"{name} must be a non-placeholder value containing at least 32 characters")

    if secrets["SECRET_KEY"] == secrets["JWT_SECRET_KEY"]:
        errors.append("SECRET_KEY and JWT_SECRET_KEY must be different")

    ai_url = urlparse(str(config.get("AI_SERVICE_URL", "")))
    if ai_url.scheme not in {"http", "https"} or not ai_url.hostname:
        errors.append("AI_SERVICE_URL must be an absolute HTTP or HTTPS URL")
    elif mode == "vlan" and ai_url.hostname in {"localhost", "127.0.0.1", "::1"}:
        errors.append("AI_SERVICE_URL must point to the AI computer in VLAN mode")

    origins = config.get("CORS_ORIGINS") or []
    if isinstance(origins, str):
        origins = [item.strip() for item in origins.split(",") if item.strip()]
    if not origins or "*" in origins:
        errors.append("CORS_ORIGINS must contain the explicit frontend origin")
    elif any(urlparse(str(origin)).scheme not in {"http", "https"} for origin in origins):
        errors.append("Every CORS_ORIGINS entry must be an absolute HTTP or HTTPS URL")

    if bool(config.get("DEBUG")):
        errors.append("FLASK_DEBUG must be disabled outside development")

    if errors:
        raise RuntimeError("Unsafe backend configuration: " + "; ".join(errors))


class Config:
    def __init__(self):
        backend_root = Path(__file__).resolve().parents[1]
        data_root = Path(os.getenv("DATA_ROOT", backend_root / "data")).resolve()
        database_default = f"sqlite:///{(data_root / 'luma.db').as_posix()}"

        self.DEPLOYMENT_MODE = os.getenv("DEPLOYMENT_MODE", "development").strip().casefold()
        self.DEBUG = os.getenv("FLASK_DEBUG", "0") == "1"
        self.SECRET_KEY = os.getenv("SECRET_KEY", "development-secret-change-me")
        self.JWT_SECRET_KEY = os.getenv("JWT_SECRET_KEY", "development-jwt-secret-change-me")
        self.JWT_ACCESS_TOKEN_EXPIRES = timedelta(hours=int(os.getenv("JWT_HOURS", "8")))
        self.SQLALCHEMY_DATABASE_URI = os.getenv("DATABASE_URL", database_default)
        self.SQLALCHEMY_TRACK_MODIFICATIONS = False
        self.MAX_CONTENT_LENGTH = int(os.getenv("MAX_CONTENT_LENGTH", str(16 * 1024 * 1024)))
        self.MAX_OUTPUT_PIXELS = int(os.getenv("MAX_OUTPUT_PIXELS", str(4_194_304)))
        self.MEDIA_ROOT = str(Path(os.getenv("MEDIA_ROOT", backend_root / "media")).resolve())
        self.UPLOAD_ROOT = str(Path(os.getenv("UPLOAD_ROOT", backend_root / "data" / "uploads")).resolve())
        self.AI_SERVICE_URL = os.getenv("AI_SERVICE_URL", "http://127.0.0.1:8000")
        self.AI_SERVICE_TOKEN = os.getenv("AI_SERVICE_TOKEN", "change-me-in-production")
        self.AI_CONNECT_TIMEOUT = float(os.getenv("AI_CONNECT_TIMEOUT", "5"))
        self.AI_READ_TIMEOUT = float(os.getenv("AI_READ_TIMEOUT", "180"))
        self.RECOVER_JOBS_ON_STARTUP = os.getenv("RECOVER_JOBS_ON_STARTUP", "1").strip().casefold() not in {
            "0",
            "false",
            "no",
        }
        self.MEDIA_TOKEN_MAX_AGE = int(os.getenv("MEDIA_TOKEN_MAX_AGE", "3600"))
        self.MEDIA_RETENTION_DAYS = int(os.getenv("MEDIA_RETENTION_DAYS", "30"))
        self.CORS_ORIGINS = [item.strip() for item in os.getenv("CORS_ORIGINS", "http://localhost:8080").split(",") if item.strip()]

