"""Utility helpers for displaying Tools API documentation snippets."""
from __future__ import annotations

from contextlib import asynccontextmanager
from typing import AsyncIterator, Iterable

from fastapi import FastAPI


def _documentation_lines() -> Iterable[str]:
    """Yield formatted lines that describe the public API surface."""
    yield "\nAPI Documentation:"
    yield "=" * 50
    yield "\n1. Convert HTML to Google Docs format:"
    yield "   POST http://localhost:8000/parse/html"
    yield '   {"html": "<h1>Hello World</h1>"}'

    yield "\n2. Parse Google Docs JSON to text:"
    yield "   POST http://localhost:8000/parse/gdocs/json"
    yield "   Content: Google Docs JSON structure"
    yield "\n   Example response:"
    yield "   {"
    yield '     "metadata": {"title": "Example Document"},'
    yield "     \"content\": {"
    yield '       "text": "Hello world",'
    yield '       "urls": ["https://example.com"],'
    yield '       "images": ["https://example.com/image.jpg"]'
    yield "     }"
    yield "   }"

    yield "\n3. Parse Google Docs file:"
    yield "   POST http://localhost:8000/parse/gdocs/file"
    yield "   Upload a Google Docs JSON file"
    yield "\n4. Docx endpoints:"
    yield "   POST http://localhost:8000/docx/parse  (multipart file upload, .docx -> text)"
    yield '   POST http://localhost:8000/docx/create (json {"text":"..."} -> returns .docx file)'
    yield "\nEndpoints are documented at: http://localhost:8000/docs"
    yield "=" * 50


def render_documentation() -> str:
    """Return the documentation banner as a single string."""
    return "\n".join(_documentation_lines())


def print_documentation() -> None:
    """Print the documentation banner to stdout."""
    print(render_documentation())


@asynccontextmanager
async def documentation_lifespan(app: FastAPI) -> AsyncIterator[None]:
    """FastAPI lifespan hook that prints the documentation banner."""
    print_documentation()
    yield
