# Tools API

A modular FastAPI microservice for n8n agents. Supports file conversion, parsing, and more via HTTP endpoints.

## Features
- Modular routers/services for tools
- Rich text HTML to Google Docs conversion
- Comprehensive text formatting support
- Async endpoints
- Centralized logging and error handling
- Docker-ready for deployment

## Endpoints
- `/parse/html` — Parse HTML to Google Docs API requests with rich text formatting
  - Supports text styles (bold, italic, colors, fonts)
  - Lists and tables
  - Complete formatting preservation
  - See `rich_text_guide.md` for details
- `/parse/markdown` — Parse Markdown to Google Docs API requests with rich formatting

- `/docx/parse` — POST multipart `.docx` file. Returns extracted plain text JSON: {"text": "..."}
- `/docx/create` — POST JSON {"text": "..."}. Returns generated `.docx` file as attachment.

## Development
```bash
# Install dependencies
pip install -r requirements.txt

# Run locally
uvicorn app.main:app --reload

# Run with Docker
# Build and start
docker-compose up --build
```

## Adding New Modules
See `code_flow.md` for step-by-step instructions.

## Background worker (queue)
This project includes a simple Redis + RQ based queue.

Run a Redis server locally (or configure `REDIS_URL` env var):

```powershell
# Windows: using docker
docker run -d --name redis -p 6379:6379 redis:7

# Then start the worker
python worker.py
```

Enqueue endpoints are available under `/parse/queue/html` and `/parse/queue/markdown`.

Docx endpoints are intended to be simple for n8n HTTP nodes:

1. To extract text from a file in n8n, use an HTTP Request node configured as multipart/form-data POST to `http://<host>:8000/docx/parse` and attach the file under the `file` field. The response will be JSON with `text`.

2. To create a .docx file, POST JSON to `http://<host>:8000/docx/create` with `{"text":"..."}` and n8n will receive an octet-stream response you can store or pass along.
