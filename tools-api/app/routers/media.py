"""Endpoints for media tooling such as yt-dlp."""
from __future__ import annotations

import base64
import json
from typing import Any, Dict, Literal
from urllib.parse import quote

from fastapi import APIRouter, HTTPException
from fastapi.encoders import jsonable_encoder
from pydantic import AnyHttpUrl, BaseModel, Field

from app.services.yt_dlp_service import DownloadResult, YtDlpServiceError, yt_dlp_service
from app.utils.logger import logger

router = APIRouter(prefix="/media", tags=["media-tools"])


class YtDlpOptions(BaseModel):
    """Subset of yt-dlp options exposed through the API."""

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


class YtDlpMetadataResponse(BaseModel):
    metadata: Dict[str, Any]


def _content_disposition(filename: str) -> str:
    encoded = quote(filename)
    return f"attachment; filename*=UTF-8''{encoded}"


def _metadata_header(metadata: Dict[str, Any]) -> str:
    json_payload = json.dumps(jsonable_encoder(metadata), ensure_ascii=False)
    return base64.b64encode(json_payload.encode("utf-8")).decode("utf-8")


@router.post("/yt-dlp", response_model=YtDlpMetadataResponse)
async def yt_dlp_endpoint(request: YtDlpRequest):
    """Fetch metadata or download media using yt-dlp with safe defaults."""

    url = str(request.url)
    options = request.options.to_yt_dlp_kwargs()

    try:
        if request.response_format == "binary":
            download: DownloadResult = yt_dlp_service.download(
                url,
                options=options,
                filename_override=request.filename,
            )
            headers = {
                "Content-Disposition": _content_disposition(download.filename),
                "X-YtDlp-Metadata": _metadata_header(download.metadata),
            }
            return _BinaryResponse(download, headers)

        metadata = yt_dlp_service.extract_info(url, options=options)
        return YtDlpMetadataResponse(metadata=jsonable_encoder(metadata))
    except YtDlpServiceError as exc:
        logger.error("yt-dlp request failed: %s", exc)
        raise HTTPException(status_code=502, detail=str(exc)) from exc


def _BinaryResponse(result: DownloadResult, headers: Dict[str, str]):
    from fastapi import Response

    return Response(content=result.content, media_type=result.content_type, headers=headers)

