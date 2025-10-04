"""Pre-flight helpers to ensure optional toolchains are ready before serving traffic."""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from app.config import settings
from app.services.cobalt_gateway import create_gateway
from app.services.cobalt_service import CobaltError
from app.services.js_tool_service import JavaScriptToolError, ensure_panosplitter_ready
from app.services.yt_dlp_service import YtDlpServiceError, ensure_media_tools_ready
from app.utils.logger import logger


def _install_python_requirements() -> None:
    requirements_path = Path(__file__).resolve().parents[3] / "requirements.txt"
    if not requirements_path.exists():
        logger.debug("No requirements.txt found at %s", requirements_path)
        return

    logger.info("Ensuring Python dependencies from %s", requirements_path)
    try:
        subprocess.run(
            [sys.executable, "-m", "pip", "install", "-r", str(requirements_path)],
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        logger.info("✅ Python dependencies installed or already satisfied.")
    except subprocess.CalledProcessError as exc:  # pragma: no cover - depends on runtime environment
        logger.warning("⚠️ Unable to install Python dependencies: %s", exc.stderr.strip() or exc)


def prepare_environment() -> None:
    """Run dependency checks for bundled tools.

    The routine logs warnings instead of raising so the API can still launch when optional
    runtimes (Node.js, yt-dlp) are unavailable. This mirrors the UX of the original desktop
    control centre where optional features degrade gracefully.
    """

    logger.info("Performing Tools API pre-flight checks…")

    _install_python_requirements()

    try:
        ensure_panosplitter_ready()
        logger.info("✅ Panosplitter is ready for JavaScript-powered slicing.")
    except JavaScriptToolError as exc:
        logger.warning("⚠️ Panosplitter unavailable: %s", exc)

    try:
        ensure_media_tools_ready()
        logger.info("✅ yt-dlp dependency detected.")
    except YtDlpServiceError as exc:
        logger.warning("⚠️ Media toolkit unavailable: %s", exc)

    try:
        gateway = create_gateway(
            remote_base_url=settings.COBALT_API_BASE_URL,
            auth_scheme=settings.COBALT_API_AUTH_SCHEME,
            auth_token=settings.COBALT_API_AUTH_TOKEN,
            timeout=settings.COBALT_API_TIMEOUT,
        )
    except CobaltError as exc:
        logger.warning("⚠️ Cobalt integrations unavailable: %s", exc)
    else:
        if gateway.has_remote and gateway.has_local:
            logger.info("✅ Cobalt remote ready with local yt-dlp fallback.")
        elif gateway.has_remote:
            logger.info("✅ Cobalt remote endpoint ready: %s", settings.COBALT_API_BASE_URL)
        elif gateway.has_local:
            logger.info("✅ Local yt-dlp fallback enabled for Cobalt downloads.")

        # Share the initialised gateway with the router so subsequent requests reuse it.
        try:  # pragma: no cover - best effort cache priming
            from app.routers import js_tools

            js_tools._cobalt_gateway = gateway
        except Exception:  # pragma: no cover - avoid hard failure during boot
            logger.debug("Unable to prime Cobalt gateway cache for routers.")

    logger.info("Pre-flight checks complete.")


__all__ = ["prepare_environment"]
