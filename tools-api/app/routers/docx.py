from fastapi import APIRouter, Request, HTTPException
from fastapi.responses import StreamingResponse
from docx.opc.exceptions import PackageNotFoundError
from app.services.docx_service import parse_docx_to_text, create_docx_from_text
from app.utils.logger import logger

router = APIRouter(prefix="/docx", tags=["docx"])

@router.post("/parse")
async def parse_docx(request: Request):
    """Upload a .docx file as raw binary data and get back extracted plain text."""
    
    # Get content type and content length from headers
    content_type = request.headers.get("content-type", "unknown")
    content_length = request.headers.get("content-length", "0")
    
    logger.info(f"Received request with content-type: {content_type}, content-length: {content_length}")
    
    # Read the raw binary body
    try:
        body = await request.body()
    except Exception as e:
        raise HTTPException(
            status_code=400,
            detail=f"Failed to read request body: {str(e)}"
        )
    
    if not body or len(body) < 1024:
        raise HTTPException(
            status_code=400,
            detail=f"Request body is empty or too small ({len(body)} bytes). Ensure n8n is sending binary data correctly."
        )
    
    logger.info(f"Received {len(body)} bytes of data")
    
    # Try to parse the document
    try:
        text = parse_docx_to_text(body)
    except PackageNotFoundError:
        raise HTTPException(
            status_code=400,
            detail="The uploaded data could not be parsed as a DOCX document. May be corrupt or invalid format."
        )
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"An error occurred during DOCX parsing: {type(e).__name__}: {str(e)}"
        )
    
    return {
        "text": text,
        "size_bytes": len(body),
        "content_type": content_type
    }
