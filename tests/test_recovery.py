# กรณีทดสอบพฤติกรรมของ recovery
from __future__ import annotations

from luma_backend import create_app, worker
from luma_backend.extensions import db
from luma_backend.models import Job, User


# สร้างค่าทดสอบที่ใช้ฐานข้อมูลเดิมร่วมกันขณะจำลองการเริ่มบริการใหม่
def config_for(tmp_path, recover: bool) -> dict:
    return {
        "TESTING": True,
        "SQLALCHEMY_DATABASE_URI": f"sqlite:///{(tmp_path / 'recovery.db').as_posix()}",
        "MEDIA_ROOT": str(tmp_path / "media"),
        "UPLOAD_ROOT": str(tmp_path / "uploads"),
        "JWT_SECRET_KEY": "test-jwt-secret-0123456789abcdef",
        "SECRET_KEY": "test-app-secret-0123456789abcdef",
        "AI_SERVICE_TOKEN": "test-service-token",
        "AI_SERVICE_URL": "http://ai.test",
        "CORS_ORIGINS": ["http://frontend.test"],
        "RECOVER_JOBS_ON_STARTUP": recover,
    }


# บันทึกงานก่อนรีสตาร์ตจำลองเพื่อทดสอบการกู้สถานะ
def create_persisted_job(tmp_path, status: str) -> str:
    app = create_app(config_for(tmp_path, recover=False))
    with app.app_context():
        user = User(username=f"student-{status}")
        user.set_password("correct-horse-battery")
        db.session.add(user)
        db.session.flush()
        # สร้างระเบียนงานที่ผูกกับผู้ใช้และค่าที่ตรวจสอบแล้ว
        job = Job(user_id=user.id, type="generate", status=status, prompt="recover this job")
        db.session.add(job)
        db.session.commit()
        job_id = job.id
        db.session.remove()
    return job_id


# ทดสอบว่าเริ่มใหม่แล้วปิดงาน processing ที่ถูกขัดจังหวะเป็น failed
def test_startup_marks_interrupted_processing_job_failed(tmp_path):
    job_id = create_persisted_job(tmp_path, "processing")

    app = create_app(config_for(tmp_path, recover=True))

    with app.app_context():
        job = db.session.get(Job, job_id)
        assert job.status == "failed"
        assert "restarted" in job.error


# ทดสอบว่าเริ่มใหม่แล้วส่งงาน queued ที่บันทึกไว้กลับเข้าคิว
def test_startup_requeues_persisted_queued_job(tmp_path, monkeypatch):
    job_id = create_persisted_job(tmp_path, "queued")
    recovered: list[str] = []
    monkeypatch.setattr(worker, "queue_job", lambda _app, recovered_id: recovered.append(recovered_id))

    create_app(config_for(tmp_path, recover=True))

    assert recovered == [job_id]
