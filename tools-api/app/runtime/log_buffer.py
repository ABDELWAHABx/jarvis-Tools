"""In-memory logging support for the desktop control center UI."""
from __future__ import annotations

import logging
import threading
from collections import deque
from typing import Callable, Deque, List, Optional


class UILogHandler(logging.Handler):
    """Logging handler that buffers recent log records for the GUI."""

    def __init__(self, max_entries: int = 500) -> None:
        super().__init__()
        self._entries: Deque[str] = deque(maxlen=max_entries)
        self._lock = threading.Lock()
        self._listeners: List[Callable[[str], None]] = []

    # Core logging API -------------------------------------------------
    def emit(self, record: logging.LogRecord) -> None:  # pragma: no cover - visual side effect
        message = self.format(record)
        with self._lock:
            self._entries.append(message)
            listeners = list(self._listeners)
        for listener in listeners:
            try:
                listener(message)
            except Exception:
                # GUI listeners should never crash the logging pipeline.
                pass

    # Data access ------------------------------------------------------
    def snapshot(self) -> List[str]:
        """Return a copy of the buffered log lines."""

        with self._lock:
            return list(self._entries)

    def tail(self, limit: Optional[int] = None) -> List[str]:
        """Return the most recent *limit* entries (all by default)."""

        with self._lock:
            if limit is None or limit >= len(self._entries):
                return list(self._entries)
            return list(self._entries)[-limit:]

    # Listener management ----------------------------------------------
    def subscribe(self, callback: Callable[[str], None]) -> None:
        """Register a callback to be notified when new log lines arrive."""

        with self._lock:
            if callback not in self._listeners:
                self._listeners.append(callback)

    def unsubscribe(self, callback: Callable[[str], None]) -> None:
        """Remove a previously registered callback."""

        with self._lock:
            if callback in self._listeners:
                self._listeners.remove(callback)

    def clear(self) -> None:
        """Remove all buffered entries."""

        with self._lock:
            self._entries.clear()


log_buffer_handler = UILogHandler(max_entries=800)

__all__ = ["UILogHandler", "log_buffer_handler"]
