# ประมวลผลงานเบื้องหลัง เชื่อมบริการ AI และบันทึกผลลัพธ์
from __future__ import annotations

import logging
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path

import requests
from flask import Flask

from .extensions import db
from .models import Job

# คิวในโปรเซสมี worker 2 ตัว ไม่ใช่คิวที่แชร์ระหว่างหลายโปรเซส

executor = ThreadPoolExecutor(max_workers=2, thread_name_prefix="luma-job")
logger = logging.getLogger(__name__)


# ทดสอบแบบทำงานทันทีได้ หรือส่งงานให้ thread pool ในการใช้งานปกติ
def queue_job(app: Flask, job_id: str) -> None:
    if app.config.get("EXECUTE_JOBS_INLINE"):
        process_job(app, job_id)
    else:
        executor.submit(process_job, app, job_id)


# เปลี่ยนสถานะงาน เรียก AI เก็บผลลัพธ์ และบันทึกความล้มเหลวพร้อมล้างไฟล์ต้นทาง
def process_job(app: Flask, job_id: str) -> None:
    source_to_remove: Path | None = None
    with app.app_context():
        job = db.session.get(Job, job_id)
        if job is None or job.status != "queued":
            return
        # บันทึกจุดเริ่มประมวลผล ค่า 15 เป็นสถานะแอปไม่ใช่ร้อยละจาก Forge
        job.status = "processing"
        job.progress = 15
        db.session.commit()

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
                raise RuntimeError(f"AI service returned {response.status_code}: {detail[:300]}")
            if not response.content or "image/" not in response.headers.get("Content-Type", ""):
                raise RuntimeError("AI service did not return a valid image response.")

            # ตั้งชื่อผลลัพธ์ตามรหัสงานและบันทึกที่ MEDIA_ROOT

            result_filename = f"{job.id}.png"
            result_path = Path(app.config["MEDIA_ROOT"]) / result_filename
            result_path.write_bytes(response.content)
            job.result_filename = result_filename
            job.provider = response.headers.get("X-LUMA-Provider", "unknown")[:80]
            returned_seed = response.headers.get("X-LUMA-Seed")
            if returned_seed:
                job.seed = int(returned_seed)
            # บันทึกสถานะสำเร็จและเวลาเมื่อจัดเก็บผลลัพธ์แล้ว
            job.status = "completed"
            job.progress = 100
            job.completed_at = datetime.now(timezone.utc)
            job.error = None
            db.session.commit()
        # ย้อน session ที่ล้มเหลวแล้วบันทึกสถานะ failed เพื่อให้ Frontend ตรวจพบ
        except Exception as exc:
            logger.exception("Job %s failed", job_id)
            db.session.rollback()
            failed_job = db.session.get(Job, job_id)
            if failed_job:
                failed_job.status = "failed"
                failed_job.error = str(exc)[:1000]
                failed_job.progress = 0
                db.session.commit()
        finally:
            # ล้างไฟล์ต้นทางชั่วคราวเมื่อจบงานทั้งกรณีสำเร็จและล้มเหลว
            if source_to_remove is not None:
                source_to_remove.unlink(missing_ok=True)

