# Code Flow & Contribution Guide

## How the System Works
- Requests hit FastAPI endpoints (routers/)
- Routers validate input, call service functions
- Services do the work (parsing, conversion, etc.)
- Responses are returned, errors logged centrally

## Adding a New Module
1. Create a new router in `app/routers/` (e.g., `convert.py`)
2. Create a corresponding service in `app/services/` (e.g., `convert_service.py`)
3. Define Pydantic models for input/output
4. Register the router in `main.py`
5. Add tests in `tests/`
6. Update `requirements.txt` if new dependencies are needed

## Adding an Open Source Tool
1. Add the tool’s package to `requirements.txt`
2. Create a service function in `app/services/` that wraps the tool’s API
3. Expose endpoints via a router in `app/routers/`
4. Validate input/output with Pydantic models
5. Add usage examples to `README.md`

### Example: Adding `python-docx` support

1. Add `python-docx` to `requirements.txt` (and `python-multipart` for file uploads).
2. Create `app/services/docx_service.py` with helper functions like `parse_docx_to_text(bytes) -> str` and `create_docx_from_text(str) -> bytes`.
3. Expose lightweight endpoints in `app/routers/docx.py`:
	- `POST /docx/parse` (multipart file upload) -> returns JSON {"text": "..."}
	- `POST /docx/create` (JSON {"text": "..."}) -> returns the .docx file as an attachment
4. Register the router in `app/main.py` using `app.include_router(docx.router)`.
5. Add examples to `README.md` showing how n8n HTTP Request nodes can call these endpoints.

This repository contains an example implementation following these steps. Use it as a template for adding other file-conversion tools.

## Prompt for Contributors
> To add a new module, follow the steps above. For open source tools, ensure you wrap their API in a service and keep routers thin. Always add tests and update documentation.

## Queue & Worker
- This project supports a Redis + RQ worker model. Add `REDIS_URL` to `.env` or run Redis locally with Docker.
- Use `python worker.py` to start a worker which will process jobs enqueued by `/parse/queue/*` endpoints.

## Google Docs BatchUpdate Output
- The parser service outputs Google Docs batchUpdate-style requests with rich text formatting support. Two main functions:
	- `parse_html_to_docs_sync(html)` - Converts HTML with full style preservation
	- `parse_markdown_to_docs_sync(md)` - Converts Markdown via HTML with formatting
- Features include:
	- Text styling (bold, italic, underline, colors)
	- Font control (family, size)
	- Block elements (headings, lists, tables)
	- Style inheritance and nesting
- See `rich_text_guide.md` for comprehensive formatting guidelines
- Typical workflow:
	1. Create a new empty document via Google Docs API
	2. Use the returned `documentId` to call `documents.batchUpdate` with the parser's requests
	3. All formatting and structure will be preserved in the Google Doc

