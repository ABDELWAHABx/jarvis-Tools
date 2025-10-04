"""Endpoints for media tooling such as yt-dlp."""
from __future__ import annotations

import asyncio
import base64
import json
from enum import Enum
from pathlib import Path
from typing import Any, Dict, Literal
from urllib.parse import quote, urlencode

from fastapi import APIRouter, HTTPException
from fastapi.concurrency import run_in_threadpool
from fastapi.encoders import jsonable_encoder
from fastapi.responses import StreamingResponse
from pydantic import AnyHttpUrl, BaseModel, ConfigDict, Field, constr, field_validator

from app.services.progress_manager import progress_manager
from app.services.yt_dlp_service import DownloadResult, YtDlpServiceError, yt_dlp_service
from app.utils.logger import logger

router = APIRouter(prefix="/media", tags=["media-tools"])


class YtDlpShortcut(str, Enum):
    """Predefined yt-dlp recipes exposed as quick API endpoints."""

    best = "best"
    fhd = "fhd"
    audio = "audio"


SHORTCUT_PRESETS: Dict[YtDlpShortcut, Dict[str, Any]] = {
    YtDlpShortcut.best: {
        "description": "Best available video with audio merged.",
        "options": {"format": "bestvideo*+bestaudio/best", "noplaylist": True},
    },
    YtDlpShortcut.fhd: {
        "description": "1080p video when available, falling back to the closest match.",
        "options": {"format": "bv*[height<=1080]+ba/b[height<=1080]", "noplaylist": True},
    },
    YtDlpShortcut.audio: {
        "description": "Audio-only download using the best available track.",
        "options": {"format": "bestaudio/best", "noplaylist": True},
    },
}


class YtDlpOptions(BaseModel):
    """Subset of yt-dlp options exposed through the API."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    format: str | None = Field(
        default=None, description="yt-dlp format selector, for example 'bestvideo+bestaudio/best'."
    )
    noplaylist: bool = Field(default=True, description="Download a single video even if the URL is a playlist.")
    playlist_items: str | None = Field(
        default=None,
        description="Select specific playlist items (yt-dlp playlist_items syntax).",
    )
    http_headers: Dict[str, str] | None = Field(
        default=None,
        description="Optional HTTP headers to send with the request (e.g. cookies or authorization).",
    )
    proxy: str | None = Field(default=None, description="Optional proxy URL passed directly to yt-dlp.")
    writesubtitles: bool = Field(
        default=False,
        description="Download subtitles alongside the main media when available.",
    )
    writeautomaticsub: bool = Field(
        default=False,
        description="Download automatically generated subtitles if authored subtitles are missing.",
    )
    subtitleslangs: list[str] | None = Field(
        default=None,
        description="List of subtitle language codes to prioritise (yt-dlp subtitleslangs option).",
    )

    @field_validator("playlist_items", "proxy", mode="before")
    @classmethod
    def _normalise_optional_strings(cls, value: Any):
        if isinstance(value, str):
            value = value.strip()
            if not value:
                return None
        return value

    @field_validator("http_headers", mode="before")
    @classmethod
    def _ensure_http_headers_dict(cls, value: Any):
        if value is None:
            return None
        if isinstance(value, dict):
            return value
        if isinstance(value, str):
            try:
                parsed = json.loads(value)
            except json.JSONDecodeError as exc:
                raise ValueError("http_headers must be a JSON object") from exc
            if not isinstance(parsed, dict):
                raise ValueError("http_headers must be a JSON object")
            return parsed
        raise ValueError("http_headers must be a mapping of header names to values")

    @field_validator("subtitleslangs", mode="before")
    @classmethod
    def _parse_subtitle_languages(cls, value: Any):
        if value is None:
            return None
        if isinstance(value, list):
            cleaned = [str(item).strip() for item in value if str(item).strip()]
            return cleaned or None
        if isinstance(value, str):
            languages = [item.strip() for item in value.split(",") if item.strip()]
            return languages or None
        raise ValueError("subtitleslangs must be a list of language codes or a comma separated string")

    def to_yt_dlp_kwargs(self) -> Dict[str, Any]:
        payload: Dict[str, Any] = {}
        if self.format:
            payload["format"] = self.format
        payload["noplaylist"] = self.noplaylist
        if self.playlist_items:
            payload["playlist_items"] = self.playlist_items
        if self.http_headers:
            payload["http_headers"] = self.http_headers
        if self.proxy:
            payload["proxy"] = self.proxy
        if self.writesubtitles:
            payload["writesubtitles"] = True
        if self.writeautomaticsub:
            payload["writeautomaticsub"] = True
        if self.subtitleslangs:
            payload["subtitleslangs"] = self.subtitleslangs
        return payload


class YtDlpRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    url: AnyHttpUrl = Field(..., description="URL understood by yt-dlp.")
    response_format: Literal["json", "binary"] = Field(
        default="json",
        description="Return metadata as JSON (default) or stream the downloaded media as binary.",
    )
    filename: str | None = Field(
        default=None,
        description="Optional filename to use when returning binary content. Defaults to yt-dlp's detected name.",
    )
    options: YtDlpOptions = Field(default_factory=YtDlpOptions, description="Advanced yt-dlp options.")
    job_id: constr(strip_whitespace=True, min_length=4, max_length=64, pattern=r"^[A-Za-z0-9_-]+$") | None = Field(
        default=None,
        description="Client-supplied identifier used to stream progress updates via server-sent events.",
    )

    @field_validator("url", mode="before")
    @classmethod
    def _normalise_url(cls, value: Any):
        if isinstance(value, str):
            trimmed = value.strip()
            if not trimmed:
                return trimmed
            if trimmed.startswith(("http://", "https://")):
                return trimmed
            if trimmed.startswith("//"):
                return f"https:{trimmed}"
            if "://" not in trimmed:
                return f"https://{trimmed}"
        return value

    @field_validator("filename", mode="before")
    @classmethod
    def _sanitise_filename(cls, value: Any):
        if value is None:
            return None
        if not isinstance(value, str):
            raise ValueError("filename must be a string")
        trimmed = value.strip()
        if not trimmed:
            return None
        safe_name = Path(trimmed).name
        if not safe_name:
            raise ValueError("filename must contain a valid file name")
        return safe_name


class YtDlpMetadataResponse(BaseModel):
    metadata: Dict[str, Any]
    shortcuts: Dict[str, str] | None = Field(
        default=None,
        description="Quick download URLs for common video/audio recipes.",
    )


def _content_disposition(filename: str) -> str:
    encoded = quote(filename)
    return f"attachment; filename*=UTF-8''{encoded}"


def _metadata_header(metadata: Dict[str, Any]) -> str:
    json_payload = json.dumps(jsonable_encoder(metadata), ensure_ascii=False)
    return base64.b64encode(json_payload.encode("utf-8")).decode("utf-8")


def _shortcut_links(url: str) -> Dict[str, str]:
    links: Dict[str, str] = {}
    for preset in YtDlpShortcut:
        if preset not in SHORTCUT_PRESETS:
            continue
        path = router.url_path_for("yt_dlp_quick_download", preset=preset.value)
        links[preset.value] = f"{path}?{urlencode({'url': url})}"
    return links


@router.post("/yt-dlp", response_model=YtDlpMetadataResponse)
async def yt_dlp_endpoint(request: YtDlpRequest):
    """Fetch metadata or download media using yt-dlp with safe defaults."""

    url = str(request.url)
    options = request.options.to_yt_dlp_kwargs()

    try:
        if request.response_format == "binary":
            progress_job_id = request.job_id
            progress_callback = None

            if progress_job_id:
                progress_manager.ensure_channel(progress_job_id)
                progress_manager.publish(
                    progress_job_id,
                    {"type": "progress", "stage": "starting", "message": "Preparing download"},
                )

                def _progress_forwarder(event: Dict[str, Any]) -> None:
                    progress_manager.publish(progress_job_id, event)

                progress_callback = _progress_forwarder

            download_kwargs: Dict[str, Any] = {
                "options": options,
                "filename_override": request.filename,
            }
            if progress_callback is not None:
                download_kwargs["progress_callback"] = progress_callback

            try:
                download: DownloadResult = await run_in_threadpool(
                    yt_dlp_service.download,
                    url,
                    **download_kwargs,
                )
            except YtDlpServiceError as exc:
                if progress_job_id:
                    progress_manager.publish(
                        progress_job_id,
                        {"type": "error", "stage": "failed", "message": str(exc)},
                    )
                logger.error("yt-dlp request failed: %s", exc)
                raise HTTPException(status_code=502, detail=str(exc)) from exc
            except Exception as exc:  # pragma: no cover - guard against unexpected failures
                if progress_job_id:
                    progress_manager.publish(
                        progress_job_id,
                        {"type": "error", "stage": "failed", "message": "Download failed"},
                    )
                logger.exception("Unexpected yt-dlp failure")
                raise
            else:
                if progress_job_id:
                    progress_manager.publish(
                        progress_job_id,
                        {"type": "progress", "stage": "packaging", "message": "Packaging download"},
                    )
                    progress_manager.publish(
                        progress_job_id,
                        {"type": "complete", "stage": "ready", "message": "Download ready"},
                    )
            finally:
                if progress_job_id:
                    progress_manager.close(progress_job_id)

            headers = {
                "Content-Disposition": _content_disposition(download.filename),
                "X-YtDlp-Metadata": _metadata_header(download.metadata),
            }
            return _BinaryResponse(download, headers)

        metadata = await run_in_threadpool(yt_dlp_service.extract_info, url, options=options)
        shortcuts = _shortcut_links(url)
        return YtDlpMetadataResponse(metadata=jsonable_encoder(metadata), shortcuts=shortcuts)
    except YtDlpServiceError as exc:
        logger.error("yt-dlp request failed: %s", exc)
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@router.get("/yt-dlp/quick/{preset}")
async def yt_dlp_quick_download(preset: YtDlpShortcut, url: AnyHttpUrl, filename: str | None = None):
    """Download media using a predefined shortcut recipe."""

    config = SHORTCUT_PRESETS.get(preset)
    if not config:
        raise HTTPException(status_code=404, detail="Unknown yt-dlp shortcut preset.")

    options = dict(config.get("options", {}))

    try:
        download: DownloadResult = await run_in_threadpool(
            yt_dlp_service.download,
            str(url),
            options=options,
            filename_override=filename,
        )
    except YtDlpServiceError as exc:
        logger.error("yt-dlp quick preset %s failed: %s", preset.value, exc)
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    headers = {
        "Content-Disposition": _content_disposition(download.filename),
        "X-YtDlp-Metadata": _metadata_header(download.metadata),
    }
    return _BinaryResponse(download, headers)


@router.get("/yt-dlp/direct")
async def yt_dlp_direct_download(url: AnyHttpUrl, format: str, filename: str | None = None):
    """Download media by specifying a yt-dlp format selector directly via query string."""

    options = {"format": format, "noplaylist": True}

    try:
        download: DownloadResult = await run_in_threadpool(
            yt_dlp_service.download,
            str(url),
            options=options,
            filename_override=filename,
        )
    except YtDlpServiceError as exc:
        logger.error("yt-dlp direct download failed: %s", exc)
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    headers = {
        "Content-Disposition": _content_disposition(download.filename),
        "X-YtDlp-Metadata": _metadata_header(download.metadata),
    }
    return _BinaryResponse(download, headers)


def _BinaryResponse(result: DownloadResult, headers: Dict[str, str]):
    from fastapi import Response

    return Response(content=result.content, media_type=result.content_type, headers=headers)


@router.get("/yt-dlp/progress/{job_id}")
async def yt_dlp_progress(job_id: str):
    """Stream yt-dlp progress updates for a specific job as Server-Sent Events."""

    try:
        progress_manager.ensure_channel(job_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    async def event_stream():
        try:
            async for event in progress_manager.iter_events(job_id):
                yield progress_manager.format_sse(event)
        except asyncio.CancelledError:  # pragma: no cover - network interruption
            logger.debug("Progress stream for %s cancelled", job_id)
            raise
        finally:
            progress_manager.close(job_id)

    response = StreamingResponse(event_stream(), media_type="text/event-stream")
    response.headers["Cache-Control"] = "no-cache"
    response.headers["X-Accel-Buffering"] = "no"
    return response

