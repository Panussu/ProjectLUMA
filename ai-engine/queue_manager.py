# ระบบจัดการคิวและควบคุมการประมวลผลพร้อมกันสำหรับ GPU (Concurrency & Queue Manager)
"""Thread-safe queue manager and GPU concurrency limiter for LUMA AI Engine."""

from __future__ import annotations

import base64
import io
import threading
import time
from contextlib import contextmanager
from typing import Any

from PIL import Image, ImageDraw

try:
    from .exceptions import ApiError
except (ImportError, ValueError):
    from exceptions import ApiError


class GenerationQueueManager:
    """Thread-safe concurrency limiter and request queue for AI image generation."""

    def __init__(self, max_concurrency: int = 1, max_capacity: int = 20, default_timeout: float = 180.0):
        self.max_concurrency = max(1, int(max_concurrency))
        self.max_capacity = max(1, int(max_capacity))
        self.default_timeout = max(1.0, float(default_timeout))
        self._semaphore = threading.Semaphore(self.max_concurrency)
        self._lock = threading.Lock()
        self._active_jobs = 0
        self._queued_jobs = 0
        self._total_completed = 0
        self._total_failed = 0
        self._total_rejected = 0
        self._total_wait_time_ms = 0.0
        self._total_exec_time_ms = 0.0
        self._start_time = time.time()
        self._active_job_start: float = 0.0

    @property
    def active_jobs(self) -> int:
        with self._lock:
            return self._active_jobs

    @property
    def queued_jobs(self) -> int:
        with self._lock:
            return self._queued_jobs

    def status(self) -> dict[str, Any]:
        with self._lock:
            completed = self._total_completed
            avg_exec = round(self._total_exec_time_ms / completed, 1) if completed > 0 else 0.0
            avg_wait = round(self._total_wait_time_ms / completed, 1) if completed > 0 else 0.0
            estimated_wait_sec = round(self._queued_jobs * (avg_exec / 1000.0), 1) if avg_exec > 0 else 0.0
            return {
                "status": "ok",
                "gpu_available": self._active_jobs < self.max_concurrency,
                "active_jobs": self._active_jobs,
                "queued_jobs": self._queued_jobs,
                "max_concurrency": self.max_concurrency,
                "queue_capacity": self.max_capacity,
                "total_completed": self._total_completed,
                "total_failed": self._total_failed,
                "total_rejected": self._total_rejected,
                "average_execution_time_ms": avg_exec,
                "average_wait_time_ms": avg_wait,
                "estimated_wait_time_seconds": estimated_wait_sec,
                "uptime_seconds": round(time.time() - self._start_time, 1),
            }

    def live_progress_simulation(self, default_steps: int = 20, include_preview: bool = False) -> dict[str, Any]:
        with self._lock:
            active = self._active_jobs > 0
            start_ts = self._active_job_start
            completed = self._total_completed
            total_exec = self._total_exec_time_ms

        if not active or start_ts <= 0.0:
            return {
                "active": False,
                "progress": 0.0,
                "progress_percent": 0.0,
                "sampling_step": 0,
                "sampling_steps": 0,
                "eta_relative": 0.0,
                "interrupted": False,
                "preview_image": None,
                "preview_available": False,
            }

        elapsed = max(0.001, time.perf_counter() - start_ts)
        avg_exec_sec = (total_exec / completed / 1000.0) if completed > 0 else 2.5
        avg_exec_sec = max(0.5, avg_exec_sec)

        ratio = elapsed / avg_exec_sec
        if ratio < 1.0:
            progress = min(0.95, max(0.05, ratio))
        else:
            progress = min(0.98, 0.95 + 0.03 * (1.0 - (1.0 / (1.0 + (ratio - 1.0)))))

        total_steps = max(1, default_steps)
        current_step = min(total_steps, max(1, int(round(progress * total_steps))))
        eta = max(0.0, round(avg_exec_sec - elapsed, 1)) if elapsed < avg_exec_sec else 0.5

        preview_b64 = None
        if include_preview:
            try:
                preview_img = Image.new("RGB", (64, 64), color=(30, 32, 48))
                draw = ImageDraw.Draw(preview_img)
                box_color = (int(60 + 100 * progress), int(100 + 80 * progress), int(200 + 40 * progress))
                draw.rectangle([8, 8, 56, 56], fill=box_color)
                buf = io.BytesIO()
                preview_img.save(buf, format="PNG")
                raw_b64 = base64.b64encode(buf.getvalue()).decode("ascii")
                preview_b64 = f"data:image/png;base64,{raw_b64}"
            except Exception:
                preview_b64 = None

        return {
            "active": True,
            "progress": round(progress, 4),
            "progress_percent": round(progress * 100.0, 1),
            "sampling_step": current_step,
            "sampling_steps": total_steps,
            "eta_relative": eta,
            "interrupted": False,
            "preview_image": preview_b64,
            "preview_available": preview_b64 is not None,
        }

    @contextmanager
    def acquire(self, timeout: float | None = None):
        req_timeout = timeout if timeout is not None else self.default_timeout
        wait_start = time.perf_counter()

        with self._lock:
            if self._queued_jobs >= self.max_capacity:
                self._total_rejected += 1
                raise ApiError(
                    "queue_full",
                    f"The AI generation queue is full ({self._queued_jobs} jobs queued). Please retry shortly.",
                    429,
                )
            self._queued_jobs += 1

        acquired = False
        try:
            acquired = self._semaphore.acquire(timeout=req_timeout)
            if not acquired:
                with self._lock:
                    self._total_rejected += 1
                raise ApiError(
                    "queue_timeout",
                    f"Request timed out waiting in the generation queue after {req_timeout}s.",
                    504,
                )
            wait_duration_ms = (time.perf_counter() - wait_start) * 1000.0
            with self._lock:
                self._queued_jobs -= 1
                self._active_jobs += 1
                self._active_job_start = time.perf_counter()
                remaining_queued = self._queued_jobs

            exec_start = time.perf_counter()
            job_stats = {
                "wait_ms": round(wait_duration_ms, 1),
                "remaining_queued": remaining_queued,
                "exec_start": exec_start,
                "exec_ms": 0.0,
            }
            try:
                yield job_stats
                exec_duration_ms = (time.perf_counter() - exec_start) * 1000.0
                job_stats["exec_ms"] = round(exec_duration_ms, 1)
                with self._lock:
                    self._total_completed += 1
                    self._total_wait_time_ms += wait_duration_ms
                    self._total_exec_time_ms += exec_duration_ms
            except Exception:
                with self._lock:
                    self._total_failed += 1
                raise
            finally:
                with self._lock:
                    self._active_jobs -= 1
                    if self._active_jobs <= 0:
                        self._active_jobs = 0
                        self._active_job_start = 0.0
                self._semaphore.release()
        finally:
            if not acquired:
                with self._lock:
                    self._queued_jobs = max(0, self._queued_jobs - 1)
