from __future__ import annotations

import os
from datetime import timedelta
from pathlib import Path


class Config:
    def __init__(self):
        backend_root = Path(__file__).resolve().parents[1]
        data_root = Path(os.getenv("DATA_ROOT", backend_root / "data")).resolve()
        database_default = f"sqlite:///{(data_root / 'luma.db').as_posix()}"

        self.SECRET_KEY = os.getenv("SECRET_KEY", "development-secret-change-me")
        self.JWT_SECRET_KEY = os.getenv("JWT_SECRET_KEY", "development-jwt-secret-change-me")
        self.JWT_ACCESS_TOKEN_EXPIRES = timedelta(hours=int(os.getenv("JWT_HOURS", "8")))
        self.SQLALCHEMY_DATABASE_URI = os.getenv("DATABASE_URL", database_default)
        self.SQLALCHEMY_TRACK_MODIFICATIONS = False
        self.MAX_CONTENT_LENGTH = int(os.getenv("MAX_CONTENT_LENGTH", str(16 * 1024 * 1024)))
        self.MEDIA_ROOT = str(Path(os.getenv("MEDIA_ROOT", backend_root / "media")).resolve())
        self.UPLOAD_ROOT = str(Path(os.getenv("UPLOAD_ROOT", backend_root / "data" / "uploads")).resolve())
        self.AI_SERVICE_URL = os.getenv("AI_SERVICE_URL", "http://127.0.0.1:8000")
        self.AI_SERVICE_TOKEN = os.getenv("AI_SERVICE_TOKEN", "change-me-in-production")
        self.AI_CONNECT_TIMEOUT = float(os.getenv("AI_CONNECT_TIMEOUT", "5"))
        self.AI_READ_TIMEOUT = float(os.getenv("AI_READ_TIMEOUT", "180"))
        self.MEDIA_TOKEN_MAX_AGE = int(os.getenv("MEDIA_TOKEN_MAX_AGE", "3600"))
        self.CORS_ORIGINS = [item.strip() for item in os.getenv("CORS_ORIGINS", "http://localhost:8080").split(",") if item.strip()]

