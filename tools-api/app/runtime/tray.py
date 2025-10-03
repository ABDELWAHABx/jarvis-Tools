"""Utilities for presenting a system tray icon while the server is running."""
from __future__ import annotations

import importlib
import importlib.util
import os
import sys
import threading
from dataclasses import dataclass
from typing import Callable, Optional


def _is_desktop_session() -> bool:
    """Return True if the current environment is likely to support a tray icon."""

    if os.name == "nt":  # Windows always exposes a system tray
        return True

    if os.name == "posix":
        if sys.platform == "darwin":  # macOS menu bar
            return True
        # On Linux require a running X11 or Wayland session
        return bool(os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY"))

    return False


def _load_tray_backend() -> Optional["_TrayBackend"]:
    """Load the optional pystray/Pillow dependencies if they are available."""

    pystray_spec = importlib.util.find_spec("pystray")
    image_spec = importlib.util.find_spec("PIL.Image")
    draw_spec = importlib.util.find_spec("PIL.ImageDraw")

    if pystray_spec is None or image_spec is None or draw_spec is None:
        return None

    pystray = importlib.import_module("pystray")
    image_module = importlib.import_module("PIL.Image")
    image_draw_module = importlib.import_module("PIL.ImageDraw")

    return _TrayBackend(pystray=pystray, image_module=image_module, image_draw_module=image_draw_module)


@dataclass
class _TrayBackend:
    pystray: "module"
    image_module: "module"
    image_draw_module: "module"


class SystemTrayController:
    """Manage an optional system tray icon that reflects server state."""

    def __init__(self) -> None:
        self._backend = _load_tray_backend() if _is_desktop_session() else None
        self._icon: Optional["pystray.Icon"] = None
        self._thread: Optional[threading.Thread] = None
        self._status: str = ""
        self._host: Optional[str] = None
        self._port: Optional[int] = None
        self._on_open: Optional[Callable[[], None]] = None
        self._on_quit: Optional[Callable[[], None]] = None

    # Public API ---------------------------------------------------------
    def start(self, host: str, port: int) -> None:
        """Initialize the tray icon in a background thread if possible."""

        self._host, self._port = host, port
        if self._backend is None or self._icon is not None:
            return

        icon = self._backend.pystray.Icon("tools-api")

        def setup(tray_icon: "pystray.Icon") -> None:
            tray_icon.title = _format_title(host, port, self._status or "Initializing")
            tray_icon.icon = self._create_icon_image("starting")
            tray_icon.visible = True
            tray_icon.menu = self._build_menu()

        self._icon = icon
        self._thread = threading.Thread(target=icon.run, kwargs={"setup": setup}, daemon=True)
        self._thread.start()

    def register_callbacks(self, *, on_open: Optional[Callable[[], None]] = None, on_quit: Optional[Callable[[], None]] = None) -> None:
        """Attach callbacks for the tray menu."""

        self._on_open = on_open
        self._on_quit = on_quit
        if self._backend is None or self._icon is None:
            return

        try:
            self._icon.menu = self._build_menu()
        except Exception:
            pass

    def update_status(self, status: str) -> None:
        """Update the tray tooltip/icon to reflect the latest status."""

        self._status = status
        if self._backend is None or self._icon is None:
            return

        try:
            self._icon.title = _format_title(self._host, self._port, status)
            state_key = _status_to_key(status)
            self._icon.icon = self._create_icon_image(state_key)
        except Exception:
            # If the desktop environment rejects updates we silently ignore it.
            pass

    def stop(self) -> None:
        """Tear down the tray icon if it was created."""

        if self._backend is None or self._icon is None:
            return

        try:
            self._icon.visible = False
            self._icon.stop()
        except Exception:
            pass
        finally:
            self._icon = None
            self._thread = None

    def is_available(self) -> bool:
        """Return True if a tray backend is available."""

        return self._backend is not None

    # Internal helpers ---------------------------------------------------
    def _create_icon_image(self, state: str) -> "PIL.Image.Image":
        backend = self._backend
        assert backend is not None  # pragma: no cover - guarded by start()
        image = backend.image_module.new("RGB", (64, 64), color=_state_color(state))
        draw = backend.image_draw_module.Draw(image)
        draw.ellipse((12, 12, 52, 52), fill=_state_indicator_color(state))
        return image

    def _build_menu(self):  # pragma: no cover - pystray menu wiring
        backend = self._backend
        if backend is None:
            return None

        items = []
        if self._on_open is not None:
            items.append(backend.pystray.MenuItem("Open Control Center", self._handle_open, default=True))

        if self._on_quit is not None:
            items.append(backend.pystray.MenuItem("Quit Tools API", self._handle_quit))

        if not items:
            return None

        return backend.pystray.Menu(*items)

    def _handle_open(self, icon: "pystray.Icon", item: "pystray.MenuItem") -> None:
        if self._on_open is not None:
            try:
                self._on_open()
            except Exception:
                pass

    def _handle_quit(self, icon: "pystray.Icon", item: "pystray.MenuItem") -> None:
        if self._on_quit is not None:
            try:
                self._on_quit()
            except Exception:
                pass


def _state_color(state: str) -> str:
    if state == "running":
        return "#E8F5E9"
    if state == "failed":
        return "#FFEBEE"
    if state == "stopped":
        return "#ECEFF1"
    return "#FFF8E1"


def _state_indicator_color(state: str) -> str:
    if state == "running":
        return "#2E7D32"
    if state == "failed":
        return "#C62828"
    if state == "stopped":
        return "#546E7A"
    return "#F9A825"


def _status_to_key(status: str) -> str:
    lowered = status.lower()
    if "run" in lowered:
        return "running"
    if "fail" in lowered:
        return "failed"
    if "stop" in lowered:
        return "stopped"
    return "starting"


def _format_title(host: Optional[str], port: Optional[int], status: str) -> str:
    address = ""
    if host and port is not None:
        address = f"{host}:{port}"
    if address:
        return f"Tools API ({address}) — {status}"
    return f"Tools API — {status}"


__all__ = ["SystemTrayController"]
