from __future__ import annotations

import json
import logging
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path

import requests
from flask import Flask

from .extensions import db
from .models import Job

executor = ThreadPoolExecutor(max_workers=2, thread_name_prefix="luma-job")
logger = logging.getLogger(__name__)


def queue_job(app: Flask, job_id: str) -> None:
    if app.config.get("EXECUTE_JOBS_INLINE"):
        process_job(app, job_id)
    else:
        executor.submit(process_job, app, job_id)


def process_job(app: Flask, job_id: str) -> None:
    source_to_remove: Path | None = None
    with app.app_context():
        job = db.session.get(Job, job_id)
        if job is None or job.status != "queued":
            return
        job.status = "processing"
        job.progress = 15
        db.session.commit()

        try:
            headers = {"X-LUMA-Service-Token": app.config["AI_SERVICE_TOKEN"]}
            timeout = (app.config["AI_CONNECT_TIMEOUT"], app.config["AI_READ_TIMEOUT"])
            base_url = app.config["AI_SERVICE_URL"].rstrip("/")

            if job.type == "generate":
                payload = {
                    "prompt": job.prompt,
                    "negative_prompt": job.negative_prompt,
                    "width": job.width,
                    "height": job.height,
                    "steps": job.steps,
                    "seed": job.seed,
                }
                if job.model:
                    payload["model"] = job.model
                if job.loras:
                    try:
                        payload["loras"] = json.loads(job.loras)
                    except Exception:
                        payload["loras"] = [l.strip() for l in job.loras.split(",") if l.strip()]
                if job.sampler:
                    payload["sampler"] = job.sampler
                if job.scheduler:
                    payload["scheduler"] = job.scheduler
                if job.cfg_scale is not None:
                    payload["cfg_scale"] = job.cfg_scale
                if job.clip_skip is not None:
                    payload["clip_skip"] = job.clip_skip
                if job.style_preset:
                    payload["style_preset"] = job.style_preset
                response = requests.post(f"{base_url}/v1/generate", json=payload, headers=headers, timeout=timeout)
            else:
                source_to_remove = Path(app.config["UPLOAD_ROOT"]) / str(job.source_filename)
                form = {"prompt": job.prompt, "strength": str(job.strength), "seed": str(job.seed)}
                if job.model:
                    form["model"] = job.model
                if job.loras:
                    form["loras"] = job.loras
                if job.sampler:
                    form["sampler"] = job.sampler
                if job.scheduler:
                    form["scheduler"] = job.scheduler
                if job.cfg_scale is not None:
                    form["cfg_scale"] = str(job.cfg_scale)
                if job.clip_skip is not None:
                    form["clip_skip"] = str(job.clip_skip)
                if job.style_preset:
                    form["style_preset"] = job.style_preset
                with source_to_remove.open("rb") as source:
                    response = requests.post(
                        f"{base_url}/v1/edit",
                        data=form,
                        files={"image": (source_to_remove.name, source, "application/octet-stream")},
                        headers=headers,
                        timeout=timeout,
                    )

            if not response.ok:
                try:
                    detail = response.json().get("error", {}).get("message", response.text)
                except ValueError:
                    detail = response.text
                raise RuntimeError(f"AI service returned {response.status_code}: {detail[:300]}")
            if not response.content or "image/" not in response.headers.get("Content-Type", ""):
                raise RuntimeError("AI service did not return a valid image response.")

            import io
            from PIL import Image
            try:
                with Image.open(io.BytesIO(response.content)) as img:
                    if img.format != "PNG":
                        raise RuntimeError("AI service result must be a PNG image.")
                    img.verify()
            except Exception as exc:
                raise RuntimeError(f"Corrupt AI image: {exc}") from exc

            result_filename = f"{job.id}.png"
            result_path = Path(app.config["MEDIA_ROOT"]) / result_filename
            result_path.write_bytes(response.content)
            job.result_filename = result_filename
            job.provider = response.headers.get("X-LUMA-Provider", "unknown")[:80]
            returned_seed = response.headers.get("X-LUMA-Seed")
            if returned_seed:
                job.seed = int(returned_seed)
            if job.status == "interrupted":
                db.session.rollback()
                return
            job.status = "completed"
            job.progress = 100
            job.completed_at = datetime.now(timezone.utc)
            job.error = None
            db.session.commit()
        except Exception as exc:
            logger.exception("Job %s stopped or failed: %s", job_id, exc)
            db.session.rollback()
            failed_job = db.session.get(Job, job_id)
            if failed_job:
                if failed_job.status == "interrupted" or "interrupt" in str(exc).lower():
                    failed_job.status = "interrupted"
                    failed_job.error = "Generation interrupted by user."
                else:
                    failed_job.status = "failed"
                    failed_job.error = str(exc)[:1000]
                failed_job.progress = 0
                failed_job.completed_at = datetime.now(timezone.utc)
                db.session.commit()
        finally:
            if source_to_remove is not None:
                source_to_remove.unlink(missing_ok=True)

