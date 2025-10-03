import pytest
from app.services import parser_service
import asyncio

@pytest.mark.asyncio
async def test_parse_html():
    html = "<h1>Hello</h1>"
    result = await parser_service.parse_html(html)
    assert isinstance(result, list)
    assert "insertText" in result[0]

@pytest.mark.asyncio
async def test_parse_markdown():
    md = "# Hello"
    result = await parser_service.parse_markdown(md)
    assert isinstance(result, list)
    assert "insertText" in result[0]
