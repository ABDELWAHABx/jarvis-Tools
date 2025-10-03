"""Background worker controller for the local queue."""
from __future__ import annotations

from queue import Empty
from threading import Event, Thread
from typing import Callable, Dict, Optional

from app.extensions import LocalQueueExtension


JobHandler = Callable[[Dict[str, str]], Dict]


class BackgroundWorkerController:
    """Manage a background thread that processes local queue jobs."""

    def __init__(self, queue_extension: LocalQueueExtension, handler: JobHandler) -> None:
        self._queue_extension = queue_extension
        self._handler = handler
        self._stop_event = Event()
        self._thread: Optional[Thread] = None

    def start(self) -> None:
        """Start the worker thread if it is not already running."""
        if self._thread and self._thread.is_alive():
            return
        self._stop_event.clear()
        self._thread = Thread(target=self._run, name="local-queue-worker", daemon=True)
        self._thread.start()

    def stop(self, timeout: float | None = 2.0) -> None:
        """Request the worker thread to stop and optionally wait for it."""
        if not self._thread:
            return
        self._stop_event.set()
        self._thread.join(timeout=timeout)
        self._thread = None

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------
    def _run(self) -> None:
        while not self._stop_event.is_set():
            try:
                job = self._queue_extension.dequeue(timeout=0.5)
            except Empty:
                continue

            job_id = job["id"]
            self._queue_extension.set_started(job_id)

            try:
                result = self._handler(job)
            except Exception as exc:  # pragma: no cover - defensive logging hook
                self._queue_extension.set_failed(job_id, str(exc))
            else:
                self._queue_extension.set_finished(job_id, result)
            finally:
                self._queue_extension.task_done()


__all__ = ["BackgroundWorkerController", "JobHandler"]
