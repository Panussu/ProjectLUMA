from __future__ import annotations

import json
import logging
import math
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path

import requests
from flask import Flask

from .extensions import db
from .models import Job

executor = ThreadPoolExecutor(max_workers=2, thread_name_prefix="luma-job")
logger = logging.getLogger(__name__)


class JobFailure(RuntimeError):
    """Error message that is safe to store on the user-visible job."""


def queue_job(app: Flask, job_id: str) -> None:
    if app.config.get("EXECUTE_JOBS_INLINE"):
        process_job(app, job_id)
    else:
        executor.submit(process_job, app, job_id)


def process_job(app: Flask, job_id: str) -> None:
    source_to_remove: Path | None = None
    result_path: Path | None = None
    saved = False
    with app.app_context():
        job = db.session.get(Job, job_id)
        if job is None or job.status != "queued":
            return
        claimed = db.session.execute(db.update(Job).where(Job.id == job_id, Job.status == "queued").values(status="processing", progress=15), execution_options={"synchronize_session": False})
        db.session.commit()
        if claimed.rowcount != 1:
            return
        db.session.refresh(job)

        try:
            headers = {
                "X-LUMA-Service-Token": app.config["AI_SERVICE_TOKEN"],
                "X-LUMA-Job-ID": str(job.id),
            }
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
                response = post_with_queue_retry(
                    f"{base_url}/v1/generate",
                    app,
                    json=payload,
                    headers=headers,
                    timeout=timeout,
                )
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
                    response = post_with_queue_retry(
                        f"{base_url}/v1/edit",
                        app,
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
                logger.warning("AI service rejected job %s with HTTP %s: %s", job_id, response.status_code, detail[:300])
                raise JobFailure(f"AI service rejected the job (HTTP {response.status_code}).")
            if not response.content or "image/" not in response.headers.get("Content-Type", ""):
                raise JobFailure("AI service did not return a valid image response.")

            import io
            from PIL import Image
            try:
                with Image.open(io.BytesIO(response.content)) as img:
                    if img.format != "PNG":
                        raise JobFailure("AI service result must be a PNG image.")
                    img.verify()
            except Exception as exc:
                raise JobFailure("AI service returned a corrupt image.") from exc

            # Check DB state before saving result
            db.session.expire_all()
            current_job = db.session.get(Job, job_id)
            if not current_job or current_job.status in {"interrupted", "cancelled"}:
                db.session.rollback()
                return

            result_filename = f"{job.id}.png"
            result_path = Path(app.config["MEDIA_ROOT"]) / result_filename
            result_path.write_bytes(response.content)

            # Re-check again before commit
            db.session.expire_all()
            current_job = db.session.get(Job, job_id)
            if not current_job or current_job.status in {"interrupted", "cancelled"}:
                if result_path.exists():
                    try:
                        result_path.unlink()
                    except OSError:
                        pass
                db.session.rollback()
                return

            # Do not dirty the Job ORM object: only the conditional SQL update
            # may complete the job. A concurrent cancellation must win cleanly.
            values = {"result_filename": result_filename,
                      "provider": response.headers.get("X-LUMA-Provider", "unknown")[:80],
                      "status": "completed", "progress": 100,
                      "completed_at": datetime.now(timezone.utc), "error": None}
            returned_seed = response.headers.get("X-LUMA-Seed")
            if returned_seed:
                try:
                    parsed_seed = int(returned_seed)
                    if 0 <= parsed_seed <= 4_294_967_295:
                        values["seed"] = parsed_seed
                except (ValueError, TypeError):
                    pass  # Optional malformed metadata must not discard a valid image.
            with db.session.no_autoflush:
                persist_ai_result(current_job, response.headers)
                completed = db.session.execute(
                    db.update(Job).where(Job.id == job_id, Job.status == "processing").values(**values),
                    execution_options={"synchronize_session": False},
                )
            if completed.rowcount != 1:
                db.session.rollback()
                result_path.unlink(missing_ok=True)
                return
            db.session.commit()
            saved = True
        except requests.Timeout:
            record_failure(job_id, "The AI service timed out before completing the job.")
        except requests.RequestException:
            record_failure(job_id, "The AI service is currently unreachable.")
        except Exception as exc:
            logger.exception("Job %s failed", job_id)
            record_failure(job_id, str(exc)[:1000] if isinstance(exc, JobFailure) else "The server could not complete this image job.")
        finally:
            if result_path is not None and not saved:
                result_path.unlink(missing_ok=True)
            if source_to_remove is not None:
                source_to_remove.unlink(missing_ok=True)


def post_with_queue_retry(url: str, app: Flask, **kwargs):
    max_retries = int(app.config.get("AI_QUEUE_MAX_RETRIES", 0))
    retry_delay = float(app.config.get("AI_QUEUE_RETRY_DELAY", 1))
    # จดตำแหน่งไฟล์เพื่อส่งข้อมูลภาพเดิมครบทุกครั้งที่ลองใหม่
    streams = []
    for value in kwargs.get("files", {}).values():
        stream = value[1] if isinstance(value, tuple) else value
        if hasattr(stream, "seek") and hasattr(stream, "tell"):
            streams.append((stream, stream.tell()))
    response = None
    for attempt in range(max_retries + 1):
        for stream, position in streams:
            stream.seek(position)
        response = requests.post(url, **kwargs)
        if response.status_code != 429 or attempt >= max_retries:
            return response
        time.sleep(retry_delay)
    return response


def persist_ai_result(job: Job, headers) -> None:
    if not job.ai_options:
        return
    result: dict = {}
    mapping = {
        "model": "X-LUMA-Model",
        "sampler": "X-LUMA-Sampler",
        "scheduler": "X-LUMA-Scheduler",
        "style_preset": "X-LUMA-Style-Preset",
    }
    for key, header in mapping.items():
        if headers.get(header):
            result[key] = headers[header]
    numeric_headers = {
        "steps": "X-LUMA-Steps",
        "clip_skip": "X-LUMA-Clip-Skip",
        "cfg_scale": "X-LUMA-CFG-Scale",
        "queue_wait_ms": "X-LUMA-Queue-Wait-Ms",
        "execution_ms": "X-LUMA-Execution-Ms",
        "queue_remaining": "X-LUMA-Queue-Remaining",
    }
    for key, header in numeric_headers.items():
        value = headers.get(header)
        if value in (None, ""):
            continue
        try:
            parsed = float(value)
        except ValueError:
            continue
        if not math.isfinite(parsed):
            continue
        result[key] = int(parsed) if key in {"steps", "clip_skip"} else parsed
    if "steps" in result:
        job.steps = result["steps"]
    job.ai_options.result_options = result



def record_failure(job_id: str, message: str) -> None:
    """Record an error only while this worker still owns a processing job."""
    db.session.rollback()
    db.session.execute(
        db.update(Job).where(Job.id == job_id, Job.status == "processing").values(
            status="failed", error=message, progress=0, completed_at=datetime.now(timezone.utc)),
        execution_options={"synchronize_session": False},
    )
    db.session.commit()
