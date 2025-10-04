"""Image tooling endpoints inspired by FUT-Coding utilities."""
from __future__ import annotations

import base64
import io
import json
from typing import Literal

from fastapi import APIRouter, File, Form, HTTPException, Query, Response, UploadFile
from PIL import Image
from pydantic import BaseModel, Field

from app.services.before_after_service import BeforeAfterError, BeforeAfterService
from app.services.halations_service import HalationsError, HalationsService
from app.utils.logger import logger

router = APIRouter(prefix="/image-tools", tags=["image-tools"])


class BeforeAfterResponse(BaseModel):
    video_base64: str = Field(..., description="Base64 encoded animation clip (MP4 or GIF).")
    filename: str
    content_type: str
    metadata: dict
    message: str | None = Field(
        default=None,
        description="Hint explaining how to customise the effect via request parameters.",
    )


class HalationsResponse(BaseModel):
    image_base64: str = Field(..., description="Base64 encoded JPEG with halations effect applied.")
    filename: str
    content_type: str
    metadata: dict
    message: str | None = None


@router.post(
    "/before-after",
    response_model=BeforeAfterResponse,
    responses={
        200: {
            "content": {
                "video/mp4": {"schema": {"type": "string", "format": "binary"}},
                "image/gif": {"schema": {"type": "string", "format": "binary"}},
            }
        }
    },
)
async def before_after_endpoint(
    before_image: UploadFile = File(..., description="Image representing the 'before' state."),
    after_image: UploadFile = File(..., description="Image representing the 'after' state."),
    frame_width: int | None = Form(
        default=None,
        description="Optional output width. Defaults to the smaller width of the uploaded images.",
    ),
    frame_height: int | None = Form(
        default=None,
        description="Optional output height. Defaults to the smaller height of the uploaded images.",
    ),
    duration_seconds: float = Form(6.0, description="Clip duration in seconds."),
    fps: int = Form(30, description="Frames per second."),
    cycles: int = Form(2, description="Number of divider sweeps across the frame."),
    line_thickness: int = Form(6, description="Thickness of the dividing line in pixels."),
    add_text: bool = Form(False, description="Overlay promotional text at the bottom of the clip."),
    overlay_text: str | None = Form(None, description="Text to render when add_text is true."),
    response_format: Literal["json", "binary"] = Query(
        "json",
        description="Return JSON with base64 animation (default) or binary stream.",
    ),
):
    """Generate a before/after swipe animation."""

    try:
        before_bytes = await before_image.read()
        after_bytes = await after_image.read()
        if not before_bytes or not after_bytes:
            raise HTTPException(status_code=400, detail="Both before and after images are required")

        before = Image.open(io.BytesIO(before_bytes))
        after = Image.open(io.BytesIO(after_bytes))

        service = BeforeAfterService(
            duration_seconds=duration_seconds,
            fps=fps,
            cycles=cycles,
            line_thickness=line_thickness,
            add_text=add_text,
            overlay_text=overlay_text,
        )

        frame_size = None
        if frame_width and frame_height:
            frame_size = (frame_width, frame_height)

        result = service.generate(before, after, frame_size=frame_size)
    except BeforeAfterError as exc:
        logger.error("Before/after generator failed: %s", exc)
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:  # pragma: no cover - Pillow parsing edge cases bubble up
        logger.exception("Unexpected error generating before/after animation")
        raise HTTPException(status_code=500, detail="Unable to generate animation") from exc

    hint_message = None
    if not any(
        [
            frame_width,
            frame_height,
            duration_seconds != 6.0,
            fps != 30,
            cycles != 2,
            line_thickness != 6,
            add_text,
        ]
    ):
        hint_message = (
            "Set form fields like frame_width, frame_height, duration_seconds, fps, cycles, or "
            "line_thickness to customise the animation. Include add_text=true and overlay_text to append captions."
        )

    if response_format == "binary":
        headers = {
            "Content-Disposition": f"attachment; filename={result.filename}",
            "X-Before-After-Metadata": base64.b64encode(
                json.dumps(result.metadata, ensure_ascii=False).encode("utf-8")
            ).decode("utf-8"),
        }
        if hint_message:
            headers["X-Before-After-Hint"] = hint_message
        return Response(content=result.content, media_type=result.content_type, headers=headers)

    payload = base64.b64encode(result.content).decode("utf-8")
    return BeforeAfterResponse(
        video_base64=payload,
        filename=result.filename,
        content_type=result.content_type,
        metadata=result.metadata,
        message=hint_message,
    )


@router.post(
    "/halations",
    response_model=HalationsResponse,
    responses={
        200: {
            "content": {
                "image/jpeg": {"schema": {"type": "string", "format": "binary"}},
            }
        }
    },
)
async def halations_endpoint(
    image: UploadFile = File(..., description="Image to enhance using the halations glow effect."),
    blur_amount: float = Form(10.0, description="Gaussian blur radius applied to the highlight mask."),
    brightness_threshold: int = Form(200, description="Brightness cut-off for selecting highlights."),
    strength: float = Form(50.0, description="Intensity of the glow overlay."),
    response_format: Literal["json", "binary"] = Query(
        "json",
        description="Return JSON (default) or binary JPEG output.",
    ),
):
    """Apply the halations glow effect to an image."""

    try:
        image_bytes = await image.read()
        if not image_bytes:
            raise HTTPException(status_code=400, detail="Image upload is required")

        pil_image = Image.open(io.BytesIO(image_bytes))
        service = HalationsService(
            blur_amount=blur_amount,
            brightness_threshold=brightness_threshold,
            strength=strength,
        )
        result = service.apply(pil_image)
    except HalationsError as exc:
        logger.error("Halations effect failed: %s", exc)
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:  # pragma: no cover - Pillow parsing edge cases bubble up
        logger.exception("Unexpected error generating halations image")
        raise HTTPException(status_code=500, detail="Unable to process image") from exc

    hint_message = None
    if blur_amount == 10.0 and brightness_threshold == 200 and strength == 50.0:
        hint_message = (
            "Adjust blur_amount, brightness_threshold, or strength form fields to fine tune the halations glow."
        )

    if response_format == "binary":
        headers = {
            "Content-Disposition": f"attachment; filename={result.filename}",
            "X-Halations-Metadata": base64.b64encode(
                json.dumps(result.metadata, ensure_ascii=False).encode("utf-8")
            ).decode("utf-8"),
        }
        if hint_message:
            headers["X-Halations-Hint"] = hint_message
        return Response(content=result.content, media_type=result.content_type, headers=headers)

    payload = base64.b64encode(result.content).decode("utf-8")
    return HalationsResponse(
        image_base64=payload,
        filename=result.filename,
        content_type=result.content_type,
        metadata=result.metadata,
        message=hint_message,
    )

