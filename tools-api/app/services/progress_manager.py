"""In-memory progress broker for streaming long running task updates."""
from __future__ import annotations

import asyncio
import json
import threading
from dataclasses import dataclass
from typing import Any, AsyncIterator, Dict

from app.utils.logger import logger


@dataclass
class _ProgressChannel:
    """Container holding the queue and loop associated with a job."""

    queue: "asyncio.Queue[dict[str, Any] | None]"
    loop: asyncio.AbstractEventLoop


class ProgressManager:
    """Tracks progress events for yt-dlp downloads and exposes them via SSE."""

    def __init__(self) -> None:
        self._channels: dict[str, _ProgressChannel] = {}
        self._lock = threading.Lock()

    def ensure_channel(self, job_id: str) -> asyncio.Queue[dict[str, Any] | None]:
        """Ensure a progress queue exists for the supplied job ID."""

        if not job_id:
            raise ValueError("job_id must be a non-empty string")

        loop = asyncio.get_running_loop()

        with self._lock:
            channel = self._channels.get(job_id)
            if channel:
                return channel.queue

            queue: "asyncio.Queue[dict[str, Any] | None]" = asyncio.Queue()
            self._channels[job_id] = _ProgressChannel(queue=queue, loop=loop)
            logger.debug("Created progress channel for job %s", job_id)
            return queue

    def publish(self, job_id: str, payload: Dict[str, Any]) -> None:
        """Publish a progress payload to the queue for the supplied job ID."""

        if not job_id:
            return

        with self._lock:
            channel = self._channels.get(job_id)

        if not channel:
            logger.debug("Discarding progress update for %s - no active listeners", job_id)
            return

        def _push() -> None:
            channel.queue.put_nowait(payload)

        channel.loop.call_soon_threadsafe(_push)

    def close(self, job_id: str) -> None:
        """Signal that no further updates will be published for the job ID."""

        if not job_id:
            return

        with self._lock:
            channel = self._channels.pop(job_id, None)

        if not channel:
            return

        logger.debug("Closing progress channel for job %s", job_id)

        def _close() -> None:
            channel.queue.put_nowait(None)

        channel.loop.call_soon_threadsafe(_close)

    async def iter_events(self, job_id: str) -> AsyncIterator[Dict[str, Any]]:
        """Yield progress events for the supplied job ID until the channel closes."""

        queue = self.ensure_channel(job_id)

        while True:
            payload = await queue.get()
            if payload is None:
                break
            yield payload

    @staticmethod
    def format_sse(payload: Dict[str, Any]) -> str:
        """Convert a payload to a string suitable for Server-Sent Events."""

        data = json.dumps(payload, ensure_ascii=False)
        return f"data: {data}\n\n"


progress_manager = ProgressManager()

