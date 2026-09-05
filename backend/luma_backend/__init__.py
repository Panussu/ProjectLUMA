from __future__ import annotations

import logging
import os
import uuid
from pathlib import Path
from typing import Any

import requests
from flask import Flask, g, jsonify, request
from flask_cors import CORS
from flask_jwt_extended import JWTManager

from .auth import auth_blueprint
from .config import Config, validate_runtime_config
from .extensions import db
from .jobs import jobs_blueprint, media_blueprint
from .worker import recover_jobs_on_startup

jwt = JWTManager()


def create_app(test_config: dict[str, Any] | None = None) -> Flask:
    app = Flask(__name__)
    app.config.from_object(Config())
    if test_config:
        app.config.update(test_config)

    validate_runtime_config(app.config)

    Path(app.config["MEDIA_ROOT"]).mkdir(parents=True, exist_ok=True)
    Path(app.config["UPLOAD_ROOT"]).mkdir(parents=True, exist_ok=True)

    logging.basicConfig(
        level=getattr(logging, os.getenv("LOG_LEVEL", "INFO").upper(), logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    db.init_app(app)
    jwt.init_app(app)
    CORS(
        app,
        resources={r"/api/*": {"origins": app.config["CORS_ORIGINS"]}},
        allow_headers=["Content-Type", "Authorization"],
        methods=["GET", "POST", "OPTIONS"],
    )

    app.register_blueprint(auth_blueprint, url_prefix="/api/v1/auth")
    app.register_blueprint(jobs_blueprint, url_prefix="/api/v1/jobs")
    app.register_blueprint(media_blueprint, url_prefix="/media")

    with app.app_context():
        db.create_all()

    @app.before_request
    def attach_request_id():
        g.request_id = request.headers.get("X-Request-ID", str(uuid.uuid4()))[:128]

    @app.after_request
    def response_headers(response):
        response.headers["X-Request-ID"] = getattr(g, "request_id", "")
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "same-origin"
        return response

    @app.get("/api/v1/health")
    def health():
        database_status = "ok"
        try:
            db.session.execute(db.text("SELECT 1"))
        except Exception:
            app.logger.exception("Database health check failed")
            database_status = "unavailable"

        ai_status = "unavailable"
        try:
            response = requests.get(f"{app.config['AI_SERVICE_URL'].rstrip('/')}/health", timeout=2)
            if response.ok:
                ai_status = "ok"
        except requests.RequestException:
            pass

        status = "ok" if database_status == "ok" else "unavailable"
        code = 200 if status == "ok" else 503
        return jsonify(
            {
                "status": status,
                "service": "luma-backend",
                "dependencies": {"database": database_status, "ai_service": ai_status},
            }
        ), code

    @app.errorhandler(413)
    def request_too_large(_error):
        return jsonify({"error": {"code": "request_too_large", "message": "The request exceeds the configured size limit."}}), 413

    @app.errorhandler(404)
    def not_found(_error):
        return jsonify({"error": {"code": "not_found", "message": "The requested endpoint does not exist."}}), 404

    @app.errorhandler(500)
    def internal_error(error):
        app.logger.error("Unhandled error: %s", error)
        return jsonify({"error": {"code": "internal_error", "message": "The server could not complete the request."}}), 500

    @jwt.unauthorized_loader
    def missing_token(message):
        return jsonify({"error": {"code": "authentication_required", "message": message}}), 401

    @jwt.invalid_token_loader
    def invalid_token(message):
        return jsonify({"error": {"code": "invalid_token", "message": message}}), 401

    @jwt.expired_token_loader
    def expired_token(_header, _payload):
        return jsonify({"error": {"code": "token_expired", "message": "The access token has expired."}}), 401

    if app.config["RECOVER_JOBS_ON_STARTUP"]:
        recover_jobs_on_startup(app)

    return app

