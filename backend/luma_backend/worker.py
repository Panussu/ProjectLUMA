# ประมวลผลงานเบื้องหลัง เชื่อมบริการ AI และบันทึกผลลัพธ์
from __future__ import annotations

import io
import logging
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path

import requests
from flask import Flask
from PIL import Image, UnidentifiedImageError

from .extensions import db
from .models import Job

# คิวในโปรเซสมี worker 2 ตัว ไม่ใช่คิวที่แชร์ระหว่างหลายโปรเซส

executor = ThreadPoolExecutor(max_workers=2, thread_name_prefix="luma-job")
logger = logging.getLogger(__name__)


# ข้อความผิดพลาดของงานที่อนุญาตให้เผยแพร่ผ่าน API
class JobProcessingError(RuntimeError):
    """A job failure message that is safe to expose through the public API."""


# ตรวจ PNG และจำนวนพิกเซลก่อนเขียนไฟล์ชั่วคราวแล้วแทนที่ปลายทาง
def save_validated_result(content: bytes, destination: Path, max_pixels: int) -> None:
    """Validate the private AI response and atomically publish a PNG result."""
    try:
        with Image.open(io.BytesIO(content)) as image:
            if image.format != "PNG":
                raise JobProcessingError("AI service result must be a PNG image.")
            if image.width * image.height > max_pixels:
                raise JobProcessingError("AI service result exceeds the configured pixel limit.")
            image.verify()
    except JobProcessingError:
        raise
    except (Image.DecompressionBombError, UnidentifiedImageError, OSError, ValueError) as exc:
        raise JobProcessingError("AI service returned corrupt or unsupported image data.") from exc

    # เขียนไฟล์ชั่วคราวก่อนแทนที่ปลายทางเพื่อลดโอกาสอ่านไฟล์ไม่ครบ

    temporary_path = destination.with_name(f".{destination.name}.{uuid.uuid4().hex}.tmp")
    try:
        temporary_path.write_bytes(content)
        temporary_path.replace(destination)
    finally:
        temporary_path.unlink(missing_ok=True)


# ทดสอบแบบทำงานทันทีได้ หรือส่งงานให้ thread pool ในการใช้งานปกติ
def queue_job(app: Flask, job_id: str) -> None:
    logger.info("Queueing job %s", job_id)
    if app.config.get("EXECUTE_JOBS_INLINE"):
        process_job(app, job_id)
    else:
        executor.submit(process_job, app, job_id)


# นำงาน queued กลับเข้าคิวและปิดงาน processing ที่ถูกขัดจังหวะเป็น failed
def recover_jobs_on_startup(app: Flask) -> None:
    """Recover durable queued jobs and close work interrupted by a restart."""
    with app.app_context():
        interrupted = db.session.scalars(
            db.select(Job).where(Job.status == "processing")
        ).all()
        queued_ids = list(
            db.session.scalars(db.select(Job.id).where(Job.status == "queued")).all()
        )
        # งานที่กำลังทำก่อนรีสตาร์ตต้องส่งใหม่ ไม่ได้ประมวลผลภาพต่อจากจุดเดิม
        for job in interrupted:
            job.status = "failed"
            job.progress = 0
            job.error = "The backend restarted before this job completed. Submit the job again."
        if interrupted:
            db.session.commit()

    if interrupted:
        logger.warning("Marked %d interrupted job(s) as failed", len(interrupted))
    # ส่งกลับเข้าคิวเฉพาะงานที่ยังรอเริ่ม
    if queued_ids:
        logger.info("Recovering %d queued job(s)", len(queued_ids))
        for job_id in queued_ids:
            queue_job(app, job_id)


# เปลี่ยนสถานะงาน เรียก AI เก็บผลลัพธ์ และบันทึกความล้มเหลวพร้อมล้างไฟล์ต้นทาง
def process_job(app: Flask, job_id: str) -> None:
    started_at = time.perf_counter()
    source_to_remove: Path | None = None
    with app.app_context():
        job = db.session.get(Job, job_id)
        if job is None or job.status != "queued":
            logger.info("Skipping job %s because it is missing or no longer queued", job_id)
            return
        # บันทึกจุดเริ่มประมวลผล ค่า 15 เป็นสถานะแอปไม่ใช่ร้อยละจาก Forge
        job.status = "processing"
        job.progress = 15
        db.session.commit()
        logger.info("Started %s job %s", job.type, job_id)

        try:
            # แนบโทเคนบริการและแยกเวลารอเชื่อมต่อออกจากเวลารอผล
            headers = {"X-LUMA-Service-Token": app.config["AI_SERVICE_TOKEN"]}
            timeout = (app.config["AI_CONNECT_TIMEOUT"], app.config["AI_READ_TIMEOUT"])
            base_url = app.config["AI_SERVICE_URL"].rstrip("/")

            # งานสร้างภาพส่ง JSON ส่วนงานแก้ไขส่งไฟล์พร้อมข้อมูลฟอร์ม

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

            # แปลง HTTP error ของบริการปลายทางเป็นข้อผิดพลาดของงาน

            if not response.ok:
                try:
                    detail = response.json().get("error", {}).get("message", response.text)
                except ValueError:
                    detail = response.text
                logger.warning("AI service rejected job %s with HTTP %s: %s", job_id, response.status_code, detail[:300])
                raise JobProcessingError(f"AI service rejected the job (HTTP {response.status_code}).")
            content_type = response.headers.get("Content-Type", "").split(";", 1)[0].strip().casefold()
            if not response.content or content_type != "image/png":
                raise JobProcessingError("AI service did not return a PNG image response.")

            returned_seed = response.headers.get("X-LUMA-Seed")
            if returned_seed:
                try:
                    parsed_seed = int(returned_seed)
                except ValueError as exc:
                    raise JobProcessingError("AI service returned an invalid seed header.") from exc
                if not 0 <= parsed_seed <= 4_294_967_295:
                    raise JobProcessingError("AI service returned an invalid seed header.")
            else:
                parsed_seed = None

            # ตั้งชื่อผลลัพธ์ตามรหัสงานและบันทึกที่ MEDIA_ROOT

            result_filename = f"{job.id}.png"
            result_path = Path(app.config["MEDIA_ROOT"]) / result_filename
            save_validated_result(response.content, result_path, app.config["MAX_OUTPUT_PIXELS"])
            job.result_filename = result_filename
            job.provider = response.headers.get("X-LUMA-Provider", "unknown")[:80]
            if parsed_seed is not None:
                job.seed = parsed_seed
            # บันทึกสถานะสำเร็จและเวลาเมื่อจัดเก็บผลลัพธ์แล้ว
            job.status = "completed"
            job.progress = 100
            job.completed_at = datetime.now(timezone.utc)
            job.error = None
            db.session.commit()
            logger.info("Completed job %s in %.2f seconds", job_id, time.perf_counter() - started_at)
        # ย้อน session ที่ล้มเหลวแล้วบันทึกสถานะ failed เพื่อให้ Frontend ตรวจพบ
        except Exception as exc:
            logger.exception("Job %s failed after %.2f seconds", job_id, time.perf_counter() - started_at)
            db.session.rollback()
            failed_job = db.session.get(Job, job_id)
            if failed_job:
                failed_job.status = "failed"
                if isinstance(exc, requests.Timeout):
                    failed_job.error = "The AI service timed out before completing the job."
                elif isinstance(exc, requests.RequestException):
                    failed_job.error = "The AI service is unavailable. Try again after it is restarted."
                elif isinstance(exc, JobProcessingError):
                    failed_job.error = str(exc)[:1000]
                else:
                    failed_job.error = "The backend could not complete this job. Check the server logs."
                failed_job.progress = 0
                db.session.commit()
        finally:
            # ล้างไฟล์ต้นทางชั่วคราวเมื่อจบงานทั้งกรณีสำเร็จและล้มเหลว
            if source_to_remove is not None:
                source_to_remove.unlink(missing_ok=True)

