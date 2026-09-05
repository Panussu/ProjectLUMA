from __future__ import annotations

import pytest

from luma_backend import create_app


def test_vlan_mode_rejects_placeholder_secrets(tmp_path):
    with pytest.raises(RuntimeError, match="Unsafe backend configuration"):
        create_app(
            {
                "TESTING": True,
                "DEPLOYMENT_MODE": "vlan",
                "SQLALCHEMY_DATABASE_URI": f"sqlite:///{(tmp_path / 'unsafe.db').as_posix()}",
                "MEDIA_ROOT": str(tmp_path / "media"),
                "UPLOAD_ROOT": str(tmp_path / "uploads"),
                "SECRET_KEY": "replace-with-a-long-random-value",
                "JWT_SECRET_KEY": "replace-with-a-different-long-random-value",
                "AI_SERVICE_TOKEN": "replace-with-one-shared-long-random-service-token",
                "AI_SERVICE_URL": "http://127.0.0.1:8000",
                "CORS_ORIGINS": ["*"],
            }
        )


def test_vlan_mode_accepts_explicit_safe_settings(tmp_path):
    app = create_app(
        {
            "TESTING": True,
            "DEPLOYMENT_MODE": "vlan",
            "SQLALCHEMY_DATABASE_URI": f"sqlite:///{(tmp_path / 'safe.db').as_posix()}",
            "MEDIA_ROOT": str(tmp_path / "media"),
            "UPLOAD_ROOT": str(tmp_path / "uploads"),
            "SECRET_KEY": "app-secret-0123456789abcdef-unique",
            "JWT_SECRET_KEY": "jwt-secret-0123456789abcdef-unique",
            "AI_SERVICE_TOKEN": "ai-token-0123456789abcdef-shared",
            "AI_SERVICE_URL": "http://192.168.1.30:8000",
            "CORS_ORIGINS": ["http://192.168.1.10"],
            "DEBUG": False,
        }
    )
    assert app.config["DEPLOYMENT_MODE"] == "vlan"
