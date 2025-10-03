from fastapi import APIRouter, HTTPException, Body, UploadFile, File
from pydantic import BaseModel, Field
from typing import Dict, List, Any
import json
from ..services.docs_parser_service import parse_google_docs_file
import tempfile
import os

router = APIRouter(
    prefix="/parse/gdocs",
    tags=["Google Docs Parser"],
    responses={404: {"description": "Not found"}},
)

class GoogleDocsParseResponse(BaseModel):
    text: str = Field(..., description="Parsed text content")
    urls: List[str] = Field(default_factory=list, description="Extracted URLs")
    images: List[str] = Field(default_factory=list, description="Extracted image URLs")

@router.post("/json", response_model=GoogleDocsParseResponse, description="Parse Google Docs JSON content")
async def parse_docs_json(
    Content: Dict = Body(..., description="Google Docs JSON content to parse")
) -> GoogleDocsParseResponse:
    """Parse Google Docs JSON content and return structured text with URLs and images separated."""
    try:
        from ..services.docs_parser_service import GoogleDocsParser
        parser = GoogleDocsParser()
        result = parser.parse_docs_json(Content)
        return {
            "text": result.text,
            "urls": result.urls,
            "images": result.images
        }
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@router.post("/file", response_model=GoogleDocsParseResponse, description="Parse Google Docs JSON file")
async def parse_docs_file(
    file: UploadFile = File(..., description="Google Docs JSON file to parse")
) -> GoogleDocsParseResponse:
    """Parse a Google Docs JSON file and return structured text with URLs and images separated."""
    try:
        with tempfile.NamedTemporaryFile(delete=False) as tmp_file:
            content = await file.read()
            tmp_file.write(content)
            tmp_file.flush()
           
            result = parse_google_docs_file(tmp_file.name)
           
            tmp_file.close()
            os.unlink(tmp_file.name)
           
            if "error" in result:
                raise ValueError(result["error"])
               
            return result
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

# Example usage in documentation
EXAMPLE_REQUEST = {
    "title": "Example Document",
    "body": {
        "content": [
            {
                "paragraph": {
                    "elements": [
                        {
                            "textRun": {
                                "content": "Hello world! Check out https://example.com",
                                "textStyle": {"bold": True}
                            }
                        }
                    ]
                }
            }
        ]
    }
}

