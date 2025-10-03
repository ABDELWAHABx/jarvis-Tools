"""Application extensions used by the Tools API service."""
from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Dict, Optional

from fastapi import APIRouter, FastAPI, HTTPException, Request
from pydantic import BaseModel

import json
import queue
from queue import Empty
import threading
import uuid


class LocalQueuePayload(BaseModel):
    """Payload accepted by the local queue enqueue endpoint."""

    html: str


class LocalQueueJobResponse(BaseModel):
    """Response returned when a job is enqueued."""

    job_id: str
    status_url: str


class LocalQueueExtension:
    """Expose simple local queue endpoints backed by an in-memory queue."""

    def __init__(self, data_dir: Path | str | None = None) -> None:
        base_dir = Path(data_dir or os.getenv("TOOLS_DATA_DIR", "./data"))
        self.data_dir = base_dir
        self.jobs_dir = self.data_dir / "jobs"
        self.jobs_dir.mkdir(parents=True, exist_ok=True)
        self._queue: "queue.Queue[Dict[str, str]]" = queue.Queue()
        self._lock = threading.Lock()

    # ------------------------------------------------------------------
    # Public API used by both FastAPI handlers and the worker controller.
    # ------------------------------------------------------------------
    def enqueue_html(self, html: str) -> str:
        job_id = uuid.uuid4().hex
        payload = {"id": job_id, "html": html}
        self._queue.put(payload)
        self._write_job(job_id, {"status": "queued"})
        return job_id

    def dequeue(self, timeout: float | None = None) -> Dict[str, str]:
        return self._queue.get(timeout=timeout)

    def task_done(self) -> None:
        self._queue.task_done()

    def set_started(self, job_id: str) -> None:
        self._write_job(job_id, {"status": "started"})

    def set_finished(self, job_id: str, result: Dict[str, Any]) -> None:
        self._write_job(job_id, {"status": "finished", "result": result})

    def set_failed(self, job_id: str, error: str) -> None:
        self._write_job(job_id, {"status": "failed", "error": error})

    def get_job(self, job_id: str) -> Optional[Dict]:
        job_file = self.jobs_dir / f"{job_id}.json"
        if not job_file.exists():
            return None
        try:
            return json.loads(job_file.read_text())
        except json.JSONDecodeError as exc:
            return {"status": "error", "error": str(exc)}


    def clear(self) -> None:
        """Reset the queue and remove persisted job state (primarily for tests)."""
        while True:
            try:
                self._queue.get_nowait()
                self._queue.task_done()
            except Empty:
                break
        for job_file in self.jobs_dir.glob('*.json'):
            if job_file.exists():
                job_file.unlink()

    # -------------------------------------------------
    # FastAPI integration helpers
    # -------------------------------------------------
    def register(self, app: FastAPI) -> None:
        router = APIRouter(prefix="/local", tags=["local queue"])

        @router.post("/queue/html", response_model=LocalQueueJobResponse)
        async def enqueue(payload: LocalQueuePayload, request: Request) -> LocalQueueJobResponse:
            job_id = self.enqueue_html(payload.html)
            status_url = request.url_for("local_job_status", job_id=job_id)
            return LocalQueueJobResponse(job_id=job_id, status_url=str(status_url))

        @router.get("/job/{job_id}", name="local_job_status")
        async def job_status(job_id: str):
            job = self.get_job(job_id)
            if job is None:
                raise HTTPException(status_code=404, detail="Job not found")
            return job

        app.include_router(router)
        app.state.local_queue = self

    # -------------------------------------------------
    # Internal helpers
    # -------------------------------------------------
    def _write_job(self, job_id: str, data: Dict[str, Any]) -> None:
        job_file = self.jobs_dir / f"{job_id}.json"
        with self._lock:
            job_file.write_text(json.dumps(data))


local_queue_extension = LocalQueueExtension()
