#!/usr/bin/env python3
"""Run the Tools API and an in-process worker, and demonstrate parsing.

This script is intended to be non-dev-friendly: it brings up the HTTP API
and a background worker in one command and prints service status and URLs.

Usage:
    python run_all.py

It will:
 - start uvicorn serving `app.main:app` on port 8000
 - start an in-process worker that processes /local/queue jobs
 - run a short self-test: POST sample HTML to /parse/html and enqueue a job
 - print job outputs and URLs

The queue used here is in-memory and not persisted across restarts. For
production, replace with Redis+RQ or a persistent queue and storage.
"""
import os
import threading
import time
import uuid
import json
import queue as pyqueue
from pathlib import Path

import uvicorn
from fastapi import FastAPI
from typing import Dict

# Import existing FastAPI app
from app.main import app  # uses your existing routers
from app.services.parser_service import parse_html_to_docs_sync
from app.routers import gdocs_parser  # Import the parsers
from contextlib import asynccontextmanager

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: Print API documentation
    print("\nAPI Documentation:")
    print("=" * 50)
    print("\n1. Convert HTML to Google Docs format:")
    print("   POST http://localhost:8000/parse/html")
    print('   {"html": "<h1>Hello World</h1>"}')
    
    print("\n2. Parse Google Docs JSON to text:")
    print("   POST http://localhost:8000/parse/gdocs/json")
    print("   Content: Google Docs JSON structure")
    print("\n   Example response:")
    print('   {')
    print('     "metadata": {"title": "Example Document"},')
    print('     "content": {')
    print('       "text": "Hello world",')
    print('       "urls": ["https://example.com"],')
    print('       "images": ["https://example.com/image.jpg"]')
    print('     }')
    print('   }')
    
    print("\n3. Parse Google Docs file:")
    print("   POST http://localhost:8000/parse/gdocs/file")
    print("   Upload a Google Docs JSON file")
    print("\n4. Docx endpoints:")
    print("   POST http://localhost:8000/docx/parse  (multipart file upload, .docx -> text)")
    print('   POST http://localhost:8000/docx/create (json {"text":"..."} -> returns .docx file)')
    print("\nEndpoints are documented at: http://localhost:8000/docs")
    print("=" * 50)
    yield
    # Shutdown: Could add cleanup code here if needed

# Register the routers
app.include_router(gdocs_parser.router)

# Register lifespan event handler
app.router.lifespan_context = lifespan

# Config
HOST = os.getenv("TOOLS_API_HOST", "127.0.0.1")
PORT = int(os.getenv("TOOLS_API_PORT", "8000"))
DATA_DIR = Path(os.getenv("TOOLS_DATA_DIR", "./data"))
JOBS_DIR = DATA_DIR / "jobs"

# In-memory queue
job_queue: pyqueue.Queue[Dict] = pyqueue.Queue()


def ensure_dirs():
    JOBS_DIR.mkdir(parents=True, exist_ok=True)


def worker_loop():
    print("[worker] started")
    while True:
        job = job_queue.get()
        job_id = job["id"]
        print(f"[worker] picked job {job_id}")
        job_file = JOBS_DIR / f"{job_id}.json"
        # mark started
        job_file.write_text(json.dumps({"status": "started"}))
        try:
            # process using parser service
            requests = parse_html_to_docs_sync(job.get("html", ""))
            out = {"status": "finished", "result": requests}
            job_file.write_text(json.dumps(out))
            print(f"[worker] finished job {job_id} (wrote {job_file})")
        except Exception as e:
            out = {"status": "failed", "error": str(e)}
            job_file.write_text(json.dumps(out))
            print(f"[worker] job {job_id} failed: {e}")


# Attach light-weight local queue endpoints to the existing app


@app.post("/local/queue/html")
async def local_enqueue_html(payload: Dict):
    html = payload.get("html", "")
    job_id = uuid.uuid4().hex
    job_queue.put({"id": job_id, "html": html})
    JOBS_DIR.joinpath(f"{job_id}.json").write_text(json.dumps({"status": "queued"}))
    return {"job_id": job_id, "status_url": f"http://{HOST}:{PORT}/local/job/{job_id}"}


@app.get("/local/job/{job_id}")
def local_job_status(job_id: str):
    job_file = JOBS_DIR / f"{job_id}.json"
    if not job_file.exists():
        return {"status": "not_found"}
    try:
        return json.loads(job_file.read_text())
    except Exception as e:
        return {"status": "error", "error": str(e)}


# Add synchronous endpoints that return Google Docs batchUpdate-style requests
@app.post("/parse/docs/html")
def parse_docs_html(payload: Dict):
    """Expects JSON: {"html": "<h1>...</h1>"}
    Returns: {"requests": [ ... ]} suitable for Google Docs documents.batchUpdate
    """
    html = payload.get("html", "")
    requests = parse_html_to_docs_sync(html)
    return {"requests": requests}

# Print API documentation at startup using FastAPI's lifespan events
from contextlib import asynccontextmanager

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: Print API documentation
    print("\nAPI Documentation:")
    print("=" * 50)
    print("\n1. Convert HTML to Google Docs format:")
    print("   POST http://localhost:8000/parse/html")
    print('   {"html": "<h1>Hello World</h1>"}')
    
    print("\n2. Parse Google Docs JSON to text:")
    print("   POST http://localhost:8000/parse/gdocs/json")
    print("   Content: Google Docs JSON structure")
    print("\n   Example response:")
    print('   {')
    print('     "metadata": {"title": "Example Document"},')
    print('     "content": {')
    print('       "text": "Hello world",')
    print('       "urls": ["https://example.com"],')
    print('       "images": ["https://example.com/image.jpg"]')
    print('     }')
    print('   }')
    
    print("\n3. Parse Google Docs file:")
    print("   POST http://localhost:8000/parse/gdocs/file")
    print("   Upload a Google Docs JSON file")
    print("\nEndpoints are documented at: http://localhost:8000/docs")
    print("=" * 50)
    yield
    # Shutdown: Could add cleanup code here if needed


@app.post("/parse/docs/markdown")
def parse_docs_markdown(payload: Dict):
    """Expects JSON: {"markdown": "# title\n..."}
    Returns: {"requests": [ ... ]}
    """
    md = payload.get("markdown", "")
    # reuse markdown -> html -> docs
    from app.services.parser_service import parse_markdown_to_docs_sync

    reqs = parse_markdown_to_docs_sync(md)
    return {"requests": reqs}


def start_worker_thread():
    t = threading.Thread(target=worker_loop, daemon=True)
    t.start()


def start_uvicorn_thread():
    def run():
        uvicorn.run(app, host=HOST, port=PORT, log_level="info")

    t = threading.Thread(target=run, daemon=True)
    t.start()
    return t


def wait_for_http_ready(timeout=10.0):
    import socket

    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            with socket.create_connection((HOST, PORT), timeout=1):
                return True
        except Exception:
            time.sleep(0.2)
    return False


def self_test():
    import requests

    base = f"http://{HOST}:{PORT}"
    print("\n--- Self-test: synchronous parse (/parse/html) ---")
    sample_html = "<h1>Test Title</h1><p>This is a paragraph from self-test.</p>"
    r = requests.post(base + "/parse/html", json={"html": sample_html}, timeout=10)
    print("POST /parse/html -> status", r.status_code)
    try:
        print("Response:", json.dumps(r.json(), indent=2))
    except Exception:
        print(r.text)

    print("\n--- Self-test: queued parse (/local/queue/html) ---")
    r2 = requests.post(base + "/local/queue/html", json={"html": sample_html}, timeout=10)
    print("POST /local/queue/html -> status", r2.status_code)
    j = r2.json()
    print("Enqueued job_id:", j.get("job_id"))
    status_url = j.get("status_url")
    print("Polling status at:", status_url)
    # poll
    for i in range(30):
        time.sleep(0.5)
        r3 = requests.get(status_url, timeout=5)
        st = r3.json()
        print(f"  attempt {i+1}: {st.get('status')}")
        if st.get("status") == "finished":
            print("Job result (first 300 chars):")
            print(json.dumps(st.get("result"))[:300])
            break


def print_summary():
    print("\n================ Services Summary ================")
    print(f"HTTP server: http://{HOST}:{PORT} (FastAPI/uvicorn)")
    print("Local queue: in-memory (endpoint: /local/queue/html)")
    print(f"Worker: in-process background thread (writing to {JOBS_DIR.resolve()})")
    print("Note: This setup is single-host, ephemeral and intended for easy testing.")
    print("For production use a persistent queue (Redis/RQ) and durable storage (S3, DB).")
    print("===================================================\n")
    # Print endpoint summary and expected parameters (mini-document)
    print("Available endpoints and parameters (mini-doc):\n")
    endpoints = [
        {"path": "/parse/html", "method": "POST", "body": {"html": "<html>...</html>"}, "desc": "Returns simple text insert requests."},
        {"path": "/parse/markdown", "method": "POST", "body": {"markdown": "# Title"}, "desc": "Returns simple text insert requests from markdown."},
        {"path": "/parse/docs/html", "method": "POST", "body": {"html": "<h1>Title</h1><p>...</p>"}, "desc": "Returns Google Docs batchUpdate requests (insertText, styles, bullets)."},
        {"path": "/parse/docs/markdown", "method": "POST", "body": {"markdown": "# Title"}, "desc": "Returns Google Docs batchUpdate requests from markdown."},
    {"path": "/docx/parse", "method": "POST", "body": {"file": "(multipart .docx file)"}, "desc": "Extract plain text from a .docx file."},
    {"path": "/docx/create", "method": "POST", "body": {"text": "Your document text"}, "desc": "Create a .docx file from plain text and return it."},
        {"path": "/local/queue/html", "method": "POST", "body": {"html": "<h1>...</h1>"}, "desc": "Enqueue a job for background processing (in-memory worker). Returns job_id and status_url."},
        {"path": "/local/job/{job_id}", "method": "GET", "body": {}, "desc": "Get job status/result JSON stored on disk under data/jobs."},
    ]
    for e in endpoints:
        print(f"{e['method']:6} {e['path']:30} - {e['desc']}")
        print("   example body:", json.dumps(e['body']))
    print("")


def main():
    ensure_dirs()
    start_worker_thread()
    start_uvicorn_thread()
    # Wait for server
    print("Starting HTTP server and worker...")
    if not wait_for_http_ready(10.0):
        print("ERROR: HTTP server did not start within timeout")
        return
    print_summary()
    print("\nRun the process in the foreground to keep services running. Ctrl+C to stop.")
    # Block forever
    try:
        while True:
            time.sleep(3600)
    except KeyboardInterrupt:
        print("Shutting down...")


if __name__ == "__main__":
    main()
