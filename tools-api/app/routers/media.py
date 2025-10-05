"""Endpoints for media tooling such as yt-dlp."""
from __future__ import annotations

import asyncio
import base64
import json
from enum import Enum
from pathlib import Path
from typing import Any, Dict, Literal

from fastapi import APIRouter, HTTPException, Request
from fastapi.concurrency import run_in_threadpool
from fastapi.encoders import jsonable_encoder
from fastapi.responses import StreamingResponse
from pydantic import AnyHttpUrl, BaseModel, ConfigDict, Field, constr, field_validator

from app.services.download_store import StoredDownload, download_store
from app.services.progress_manager import progress_manager
from app.services.yt_dlp_service import DownloadResult, YtDlpServiceError, yt_dlp_service
from app.utils.logger import logger

router = APIRouter(prefix="/media", tags=["media-tools"])


class YtDlpResponseFormat(str, Enum):
    metadata = "metadata"
    download = "download"


class YtDlpDownloadMode(str, Enum):
    video = "video"
    audio = "audio"
    subtitles = "subtitles"


class YtDlpSubtitleSource(str, Enum):
    original = "original"
    auto = "auto"


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
    response_format: YtDlpResponseFormat = Field(
        default=YtDlpResponseFormat.metadata,
        description="Return metadata or persist a download for retrieval.",
    )
    filename: str | None = Field(
        default=None,
        description="Optional filename to use when returning binary content. Defaults to yt-dlp's detected name.",
    )
    mode: YtDlpDownloadMode | None = Field(
        default=None,
        description="Download mode to execute when response_format='download'.",
    )
    format_id: str | None = Field(
        default=None,
        description="Specific yt-dlp format identifier selected from metadata.",
    )
    subtitle_languages: list[str] | None = Field(
        default=None,
        description="Subtitle language codes to download when mode='subtitles'.",
    )
    subtitle_source: YtDlpSubtitleSource = Field(
        default=YtDlpSubtitleSource.original,
        description="Use original author subtitles or automatically generated captions.",
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
    available_subtitles: Dict[str, list[str]] = Field(
        default_factory=dict,
        description="Convenience map listing subtitle languages grouped by source type.",
    )


class YtDlpDownloadDescriptor(BaseModel):
    id: str
    filename: str
    content_type: str
    filesize: int
    url: str
    metadata: Dict[str, Any]


class YtDlpDownloadResponse(BaseModel):
    metadata: Dict[str, Any]
    download: YtDlpDownloadDescriptor


def _metadata_header(metadata: Dict[str, Any]) -> str:
    json_payload = json.dumps(jsonable_encoder(metadata), ensure_ascii=False)
    return base64.b64encode(json_payload.encode("utf-8")).decode("utf-8")


def _subtitle_language_map(metadata: Dict[str, Any]) -> Dict[str, list[str]]:
    subtitles: Dict[str, Any] = {}
    if isinstance(metadata.get("subtitles"), dict):
        subtitles = metadata["subtitles"]

    automatic: Dict[str, Any] = {}
    if isinstance(metadata.get("automatic_captions"), dict):
        automatic = metadata["automatic_captions"]

    def _extract_languages(source: Dict[str, Any]) -> list[str]:
        languages: set[str] = set()
        for key, value in source.items():
            if not key:
                continue
            languages.add(str(key))
            if isinstance(value, dict):
                alt = value.get("name")
                if alt:
                    languages.add(str(alt))
        return sorted(languages)

    payload: Dict[str, list[str]] = {}
    original = _extract_languages(subtitles)
    if original:
        payload[YtDlpSubtitleSource.original.value] = original
    automatic_languages = _extract_languages(automatic)
    if automatic_languages:
        payload[YtDlpSubtitleSource.auto.value] = automatic_languages
    return payload


async def _handle_download(request: YtDlpRequest, url: str, options: Dict[str, Any], http_request: Request) -> YtDlpDownloadResponse:
    mode = request.mode or YtDlpDownloadMode.video
    progress_job_id = request.job_id

    if mode != YtDlpDownloadMode.subtitles and request.format_id:
        options["format"] = request.format_id
    elif mode == YtDlpDownloadMode.video:
        options.setdefault("format", "bestvideo*+bestaudio/best")
    elif mode == YtDlpDownloadMode.audio:
        options.setdefault("format", "bestaudio/best")

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

    try:
        if mode == YtDlpDownloadMode.subtitles:
            subtitle_options = dict(options)
            if request.subtitle_languages:
                subtitle_options["subtitleslangs"] = request.subtitle_languages
            if request.subtitle_source == YtDlpSubtitleSource.auto:
                subtitle_options["writeautomaticsub"] = True
                subtitle_options.pop("writesubtitles", None)
            else:
                subtitle_options["writesubtitles"] = True
                subtitle_options.pop("writeautomaticsub", None)

            download = await run_in_threadpool(
                yt_dlp_service.download_subtitles,
                url,
                options=subtitle_options,
                filename_override=request.filename,
            )
        else:
            download_kwargs: Dict[str, Any] = {
                "options": options,
                "filename_override": request.filename,
            }
            if progress_callback is not None:
                download_kwargs["progress_callback"] = progress_callback

            download = await run_in_threadpool(
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

    download.metadata = download.metadata or {}
    download.metadata.setdefault("mode", mode.value)

    stored = _persist_download(download)
    return _build_download_response(stored, download.metadata, http_request)


def _persist_download(download: DownloadResult) -> StoredDownload:
    metadata = dict(jsonable_encoder(download.metadata or {}))
    metadata.setdefault("filename", download.filename)
    metadata.setdefault("content_type", download.content_type)
    metadata.setdefault("filesize", len(download.content))
    stored = download_store.store(
        filename=download.filename,
        content=download.content,
        content_type=download.content_type,
        metadata=metadata,
    )
    return stored


def _build_download_response(stored: StoredDownload, metadata: Dict[str, Any], request: Request) -> YtDlpDownloadResponse:
    download_url = str(request.url_for("yt_dlp_download_file", file_id=stored.file_id))
    download_payload = YtDlpDownloadDescriptor(
        id=stored.file_id,
        filename=stored.filename,
        content_type=stored.content_type,
        filesize=stored.path.stat().st_size,
        url=download_url,
        metadata=jsonable_encoder(stored.metadata),
    )
    return YtDlpDownloadResponse(
        metadata=jsonable_encoder(metadata),
        download=download_payload,
    )


@router.get("/yt-dlp/files/{file_id}")
async def yt_dlp_download_file(file_id: str):
    try:
        stored = download_store.retrieve(file_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Download not found") from exc

    response = FileResponse(
        stored.path,
        media_type=stored.content_type,
        filename=stored.filename,
    )
    response.headers["X-YtDlp-Metadata"] = _metadata_header(stored.metadata)
    return response


@router.post("/yt-dlp", response_model=YtDlpMetadataResponse | YtDlpDownloadResponse)
async def yt_dlp_endpoint(payload: YtDlpRequest, request: Request):
    """Fetch metadata or persist media downloads using yt-dlp with safe defaults."""

    url = str(payload.url)
    options = payload.options.to_yt_dlp_kwargs()

    try:
        if payload.response_format == YtDlpResponseFormat.download:
            if payload.mode is None:
                raise HTTPException(status_code=400, detail="Download mode is required for downloads")

            return await _handle_download(payload, url, options, request)

        metadata = await run_in_threadpool(yt_dlp_service.extract_info, url, options=options)
        available_subtitles = _subtitle_language_map(metadata)
        return YtDlpMetadataResponse(
            metadata=jsonable_encoder(metadata),
            available_subtitles=available_subtitles,
        )
    except YtDlpServiceError as exc:
        logger.error("yt-dlp request failed: %s", exc)
        raise HTTPException(status_code=502, detail=str(exc)) from exc


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

