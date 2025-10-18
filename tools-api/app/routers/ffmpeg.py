"""FFmpeg powered media conversion endpoints."""
from __future__ import annotations

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from starlette.background import BackgroundTask

from app.services.ffmpeg_service import ConversionResult, FfmpegServiceError, ffmpeg_service

router = APIRouter(prefix="/media/ffmpeg", tags=["ffmpeg"])


class FormatListResponse(BaseModel):
    inputs: list[str] = Field(default_factory=list, description="Formats FFmpeg can read.")
    outputs: list[str] = Field(default_factory=list, description="Formats FFmpeg can write.")
    common: list[str] = Field(default_factory=list, description="Formats available for both input and output.")


@router.get("/formats", response_model=FormatListResponse)
async def list_formats() -> FormatListResponse:
    """Return cached FFmpeg format capabilities."""

    try:
        formats = await run_in_threadpool(ffmpeg_service.list_formats)
    except FfmpegServiceError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc

    return FormatListResponse.model_validate(formats)


@router.post("/convert")
async def convert_media(
    file: UploadFile = File(..., description="Media file to convert."),
    target_format: str = Form(..., description="Desired output container/format."),
    source_format: str | None = Form(None, description="Optional hint for the input container."),
    sample_rate: int = Form(24000, description="Input sample rate (Hz), for raw PCM/S16LE etc."),   # NEW
    channels: int = Form(1, description="Number of input channels, for PCM.")                       # NEW
) -> FileResponse:
    """Convert media using FFmpeg and stream back the resulting file."""

    await file.seek(0)
    try:
        # Pass new params to the service call
        result: ConversionResult = await run_in_threadpool(
            ffmpeg_service.convert_upload,
            file,
            source_format=source_format,
            target_format=target_format,
            sample_rate=sample_rate,   # NEW
            channels=channels          # NEW
        )
    except FfmpegServiceError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    finally:
        await file.close()

    background = BackgroundTask(ffmpeg_service.cleanup_directory, result.workdir)
    return FileResponse(
        path=result.output_path,
        filename=result.filename,
        media_type=result.media_type,
        background=background,
    )
