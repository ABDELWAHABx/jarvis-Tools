from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from pydantic import BaseModel, Field

from app.services.js_tool_service import JavaScriptToolError, run_panosplitter
from app.utils.logger import logger

router = APIRouter(prefix="/js-tools", tags=["javascript-tools"])


class ImagePayload(BaseModel):
    filename: str
    content_type: str
    base64: str = Field(..., description="Base64 encoded image data")
    width: int | None = None
    height: int | None = None


class ZipPayload(BaseModel):
    filename: str
    base64: str = Field(..., description="Base64 encoded zip archive")
    content_type: str


class PanosplitterMetadata(BaseModel):
    mode: str
    slice_count: int
    slice_width: int
    slice_height: int
    scaled_width: int
    scaled_height: int
    original_filename: str


class PanosplitterResponse(BaseModel):
    metadata: PanosplitterMetadata
    zip_file: ZipPayload
    slices: list[ImagePayload]
    full_view: ImagePayload


@router.post("/panosplitter", response_model=PanosplitterResponse)
async def panosplitter_endpoint(
    image: UploadFile = File(..., description="Panorama image to split"),
    high_res: bool = Form(False, description="Use the high resolution splitting mode"),
):
    """Split a panorama image into Instagram-friendly slices using the JavaScript toolchain."""

    try:
        image_bytes = await image.read()
        if not image_bytes:
            raise HTTPException(status_code=400, detail="Uploaded file is empty")

        result = run_panosplitter(image_bytes, high_res=high_res, filename=image.filename)
        return result
    except JavaScriptToolError as exc:
        logger.error("JavaScript tool failed: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    except Exception as exc:  # pragma: no cover - FastAPI will re-raise as HTTP 500
        logger.exception("Unexpected error running panosplitter")
        raise HTTPException(status_code=500, detail="Failed to process image") from exc
