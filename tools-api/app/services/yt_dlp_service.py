"""Service wrapper around yt-dlp to expose downloads via FastAPI."""
from __future__ import annotations

import base64
import json
import mimetypes
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict

from app.utils.logger import logger


class YtDlpServiceError(RuntimeError):
    """Raised when yt-dlp fails to process a request."""


@dataclass
class DownloadResult:
    """Container for downloaded binary payloads."""

    content: bytes
    filename: str
    content_type: str
    metadata: Dict[str, Any]


def _ensure_yt_dlp() -> Any:
    """Import yt_dlp lazily so requirements remain optional for some commands."""

    try:
        import yt_dlp  # type: ignore
    except ImportError as exc:  # pragma: no cover - fast failure when dependency missing
        raise YtDlpServiceError(
            "yt-dlp is not installed. Install it via 'pip install yt-dlp' to enable the media tools."
        ) from exc

    return yt_dlp


class YtDlpService:
    """Thin wrapper around yt-dlp with opinionated defaults."""

    def __init__(self, *, base_options: Dict[str, Any] | None = None) -> None:
        self.base_options = base_options or {}

    def _build_options(self, overrides: Dict[str, Any]) -> Dict[str, Any]:
        options: Dict[str, Any] = {
            "quiet": True,
            "no_warnings": True,
            "ignoreerrors": False,
            "concurrent_fragment_downloads": 3,
        }
        options.update(self.base_options)
        options.update({k: v for k, v in overrides.items() if v is not None})
        return options

    def extract_info(self, url: str, *, options: Dict[str, Any]) -> Dict[str, Any]:
        """Return metadata about the supplied URL without downloading content."""

        yt_dlp = _ensure_yt_dlp()
        merged_options = self._build_options({"skip_download": True, **options})

        logger.debug("Fetching yt-dlp metadata for %s with options %s", url, merged_options)
        try:
            with yt_dlp.YoutubeDL(merged_options) as ydl:
                info = ydl.extract_info(url, download=False)
        except Exception as exc:  # pragma: no cover - yt-dlp raises many custom errors
            logger.error("yt-dlp metadata extraction failed: %s", exc)
            raise YtDlpServiceError(str(exc)) from exc

        return info

    def download(self, url: str, *, options: Dict[str, Any], filename_override: str | None = None) -> DownloadResult:
        """Download the media payload and return the bytes plus metadata."""

        yt_dlp = _ensure_yt_dlp()

        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            merged_options = self._build_options({
                "skip_download": False,
                "outtmpl": str(tmp_path / "%(title)s.%(ext)s"),
                **options,
            })

            logger.debug("Downloading media via yt-dlp for %s with options %s", url, merged_options)
            try:
                with yt_dlp.YoutubeDL(merged_options) as ydl:
                    info = ydl.extract_info(url, download=True)
            except Exception as exc:  # pragma: no cover - yt-dlp raises many custom errors
                logger.error("yt-dlp download failed: %s", exc)
                raise YtDlpServiceError(str(exc)) from exc

            download_path = self._resolve_download_path(info)
            if download_path is None:
                logger.error("yt-dlp did not report a downloaded file path")
                raise YtDlpServiceError("Download completed but no file path was reported by yt-dlp")

            path = Path(download_path)
            if not path.exists():
                logger.error("yt-dlp reported file %s but it does not exist", path)
                raise YtDlpServiceError("yt-dlp reported a downloaded file that could not be found")

            filename = filename_override or path.name
            content = path.read_bytes()
            content_type = mimetypes.guess_type(filename)[0] or "application/octet-stream"

            metadata = self._serializable_metadata(info)

            return DownloadResult(content=content, filename=filename, content_type=content_type, metadata=metadata)

    def _resolve_download_path(self, info: Dict[str, Any]) -> str | None:
        """Find the best guess at the downloaded file path from a yt-dlp info dict."""

        if "_filename" in info and info["_filename"]:
            return str(info["_filename"])

        requested_downloads = info.get("requested_downloads")
        if isinstance(requested_downloads, list) and requested_downloads:
            filepath = requested_downloads[0].get("filepath")
            if filepath:
                return str(filepath)

        # Some playlist requests include entries under "entries".
        entries = info.get("entries")
        if isinstance(entries, list) and entries:
            first_entry = entries[0]
            if isinstance(first_entry, dict):
                return self._resolve_download_path(first_entry)

        return None

    def _serializable_metadata(self, info: Dict[str, Any]) -> Dict[str, Any]:
        """Ensure the metadata can be encoded as JSON for headers/response bodies."""

        try:
            json.dumps(info)
            return info
        except TypeError:
            safe_payload = json.loads(json.dumps(info, default=self._encode_binary_fields))
            return safe_payload

    def _encode_binary_fields(self, value: Any) -> str:
        """Convert non-serializable values into JSON friendly representations."""

        if isinstance(value, (bytes, bytearray)):
            return base64.b64encode(value).decode("utf-8")
        return str(value)


# Shared singleton so FastAPI routes can import and reuse it.
yt_dlp_service = YtDlpService()

