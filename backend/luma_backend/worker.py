from __future__ import annotations

import logging
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


def queue_job(app: Flask, job_id: str) -> None:
    logger.info("Queueing job %s", job_id)
    if app.config.get("EXECUTE_JOBS_INLINE"):
        process_job(app, job_id)
    else:
        executor.submit(process_job, app, job_id)


def recover_jobs_on_startup(app: Flask) -> None:
    """Recover durable queued jobs and close work interrupted by a restart."""
    with app.app_context():
        interrupted = db.session.scalars(
            db.select(Job).where(Job.status == "processing")
        ).all()
        queued_ids = list(
            db.session.scalars(db.select(Job.id).where(Job.status == "queued")).all()
        )
        for job in interrupted:
            job.status = "failed"
            job.progress = 0
            job.error = "The backend restarted before this job completed. Submit the job again."
        if interrupted:
            db.session.commit()

    if interrupted:
        logger.warning("Marked %d interrupted job(s) as failed", len(interrupted))
    if queued_ids:
        logger.info("Recovering %d queued job(s)", len(queued_ids))
        for job_id in queued_ids:
            queue_job(app, job_id)


def process_job(app: Flask, job_id: str) -> None:
    started_at = time.perf_counter()
    source_to_remove: Path | None = None
    with app.app_context():
        job = db.session.get(Job, job_id)
        if job is None or job.status != "queued":
            logger.info("Skipping job %s because it is missing or no longer queued", job_id)
            return
        job.status = "processing"
        job.progress = 15
        db.session.commit()
        logger.info("Started %s job %s", job.type, job_id)

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
                response = requests.post(f"{base_url}/v1/generate", json=payload, headers=headers, timeout=timeout)
            else:
                source_to_remove = Path(app.config["UPLOAD_ROOT"]) / str(job.source_filename)
                form = {"prompt": job.prompt, "strength": str(job.strength), "seed": str(job.seed)}
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

            result_filename = f"{job.id}.png"
            result_path = Path(app.config["MEDIA_ROOT"]) / result_filename
            result_path.write_bytes(response.content)
            job.result_filename = result_filename
            job.provider = response.headers.get("X-LUMA-Provider", "unknown")[:80]
            returned_seed = response.headers.get("X-LUMA-Seed")
            if returned_seed:
                job.seed = int(returned_seed)
            job.status = "completed"
            job.progress = 100
            job.completed_at = datetime.now(timezone.utc)
            job.error = None
            db.session.commit()
            logger.info("Completed job %s in %.2f seconds", job_id, time.perf_counter() - started_at)
        except Exception as exc:
            logger.exception("Job %s failed after %.2f seconds", job_id, time.perf_counter() - started_at)
            db.session.rollback()
            failed_job = db.session.get(Job, job_id)
            if failed_job:
                failed_job.status = "failed"
                failed_job.error = str(exc)[:1000]
                failed_job.progress = 0
                db.session.commit()
        finally:
            if source_to_remove is not None:
                source_to_remove.unlink(missing_ok=True)

