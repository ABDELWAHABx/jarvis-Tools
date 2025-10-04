"""Local fallback implementation for Cobalt downloads powered by yt-dlp."""
from __future__ import annotations

import asyncio
import base64
import json
from dataclasses import dataclass
from typing import Any, Dict, Optional

from app.services.cobalt_service import CobaltBinaryResult, CobaltError
from app.services.yt_dlp_service import (
    DownloadResult,
    YtDlpService,
    YtDlpServiceError,
    ensure_media_tools_ready,
)
from app.utils.logger import logger


DEFAULT_AUDIO_FORMAT = "mp3"
DEFAULT_VIDEO_QUALITY = "1080"


@dataclass
class LocalProcessResult:
    """Structured result returned by the local Cobalt fallback."""

    payload: Dict[str, Any]
    binary: Optional[CobaltBinaryResult]


class LocalCobaltService:
    """Translate common Cobalt payloads into local yt-dlp invocations."""

    def __init__(self, yt_dlp_service: YtDlpService) -> None:
        self._yt_dlp = yt_dlp_service

    def check_dependencies(self) -> None:
        """Ensure yt-dlp is importable before accepting requests."""

        ensure_media_tools_ready()

    async def process(
        self,
        payload: Dict[str, Any],
        *,
        expect_binary: bool,
        filename_override: Optional[str] = None,
    ) -> LocalProcessResult:
        """Execute the supplied request using the local yt-dlp toolchain."""

        url = payload.get("url")
        if not url:
            raise CobaltError("A URL is required to process media")

        mode = self._resolve_mode(payload)
        logger.info("Processing Cobalt fallback (%s) for %s", mode, url)

        options = self._build_options(payload, mode)

        if expect_binary:
            download = await self._run_download(url, options, filename_override)
            metadata = self._build_metadata_from_download(download, mode)
            binary = self._build_binary_response(download, metadata)
            return LocalProcessResult(payload=metadata, binary=binary)

        info = await self._run_metadata(url, options)
        metadata = self._build_metadata_from_info(info, mode)
        return LocalProcessResult(payload=metadata, binary=None)

    async def _run_download(
        self,
        url: str,
        options: Dict[str, Any],
        filename_override: Optional[str],
    ) -> DownloadResult:
        """Execute a blocking download in a worker thread."""

        return await asyncio.to_thread(
            self._yt_dlp.download,
            url,
            options=options,
            filename_override=filename_override,
        )

    async def _run_metadata(self, url: str, options: Dict[str, Any]) -> Dict[str, Any]:
        """Resolve metadata for a URL using a worker thread."""

        return await asyncio.to_thread(
            self._yt_dlp.extract_info,
            url,
            options=options,
        )

    def _resolve_mode(self, payload: Dict[str, Any]) -> str:
        """Determine the desired download mode from the payload."""

        mode = (payload.get("downloadMode") or "auto").lower()
        if mode in {"audio", "video", "metadata"}:
            return mode

        # Legacy cobalt shortcuts frequently set "preset" instead of downloadMode.
        preset = (payload.get("preset") or "").lower()
        if preset.startswith("youtube-audio") or "audio" in preset:
            return "audio"
        if preset.startswith("youtube-video") or "video" in preset:
            return "video"

        return "auto"

    def _build_options(self, payload: Dict[str, Any], mode: str) -> Dict[str, Any]:
        """Translate a subset of Cobalt options to yt-dlp flags."""

        options: Dict[str, Any] = {}

        # yt-dlp handles metadata extraction without special flags – keep parity for downloads.
        if mode == "audio":
            options.update(self._audio_options(payload))
        elif mode == "video":
            options.update(self._video_options(payload))
        else:  # auto/metadata
            options.update(self._auto_options(payload))

        # Common toggles.
        if payload.get("youtubeHLS"):
            options.setdefault("format", "bestaudio/best")

        if payload.get("disableMetadata"):
            options.setdefault("noprogress", True)

        return options

    def _audio_options(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        format_override = payload.get("audioFormat") or DEFAULT_AUDIO_FORMAT
        bitrate = payload.get("audioBitrate")

        postprocessor = {
            "key": "FFmpegExtractAudio",
            "preferredcodec": format_override,
        }
        if bitrate:
            postprocessor["preferredquality"] = str(bitrate)

        return {
            "format": "bestaudio/best",
            "postprocessors": [postprocessor],
        }

    def _video_options(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        quality = str(payload.get("videoQuality") or DEFAULT_VIDEO_QUALITY)
        codec = payload.get("youtubeVideoCodec")

        format_parts = [f"bv*[height<=?{quality}]"]
        if codec:
            format_parts[0] += f"[vcodec^={codec}]"
        format_selector = "+".join([format_parts[0], "ba"]) + "/best"

        return {"format": format_selector}

    def _auto_options(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        return {"format": "bv*+ba/b"}

    def _build_metadata_from_download(self, download: DownloadResult, mode: str) -> Dict[str, Any]:
        metadata = dict(download.metadata or {})
        metadata.update(
            {
                "status": "local",
                "mode": mode,
                "filename": download.filename,
                "contentType": download.content_type,
                "filesize": len(download.content),
                "source": "yt-dlp",
                "backend": "local",
            }
        )
        return metadata

    def _build_binary_response(
        self, download: DownloadResult, metadata: Dict[str, Any]
    ) -> CobaltBinaryResult:
        payload = {k: v for k, v in metadata.items() if k != "content"}
        encoded_metadata = base64.b64encode(
            json.dumps(payload, ensure_ascii=False).encode("utf-8")
        ).decode("utf-8")

        return CobaltBinaryResult(
            content=download.content,
            filename=download.filename,
            content_type=download.content_type,
            metadata=payload,
            encoded_metadata=encoded_metadata,
        )

    def _build_metadata_from_info(self, info: Dict[str, Any], mode: str) -> Dict[str, Any]:
        metadata = self._yt_dlp._serializable_metadata(info)
        metadata.update(
            {
                "status": "local",
                "mode": mode,
                "source": "yt-dlp",
                "backend": "local",
                "title": info.get("title"),
                "url": info.get("webpage_url") or info.get("original_url"),
            }
        )
        return metadata


def create_local_cobalt_service(yt_dlp_service: YtDlpService) -> LocalCobaltService | None:
    """Factory helper that returns a ready-to-use local fallback if possible."""

    service = LocalCobaltService(yt_dlp_service)
    try:
        service.check_dependencies()
    except YtDlpServiceError:
        logger.warning("yt-dlp is unavailable – local Cobalt fallback disabled.")
        return None

    return service


__all__ = [
    "LocalCobaltService",
    "LocalProcessResult",
    "create_local_cobalt_service",
]
