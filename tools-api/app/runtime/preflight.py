"""Pre-flight helpers to ensure optional toolchains are ready before serving traffic."""
from __future__ import annotations

from app.services.js_tool_service import JavaScriptToolError, ensure_panosplitter_ready
from app.services.yt_dlp_service import YtDlpServiceError, ensure_media_tools_ready
from app.utils.logger import logger


def prepare_environment() -> None:
    """Run dependency checks for bundled tools.

    The routine logs warnings instead of raising so the API can still launch when optional
    runtimes (Node.js, yt-dlp) are unavailable. This mirrors the UX of the original desktop
    control centre where optional features degrade gracefully.
    """

    logger.info("Performing Tools API pre-flight checks…")

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

    logger.info("Pre-flight checks complete.")


__all__ = ["prepare_environment"]
