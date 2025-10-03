"""CLI helpers for orchestrating the Tools API demo stack."""
from __future__ import annotations

import os
import threading
import time
from typing import Tuple

import uvicorn

from app.extensions import local_queue_extension
from app.main import app
from app.runtime.documentation import print_documentation
from app.runtime.worker import BackgroundWorkerController
from app.services.parser_service import parse_html_to_docs_sync


HOST_ENV = "TOOLS_API_HOST"
PORT_ENV = "TOOLS_API_PORT"

def _get_host_port() -> Tuple[str, int]:
    host = os.getenv(HOST_ENV, "127.0.0.1")
    port = int(os.getenv(PORT_ENV, "8000"))
    return host, port


def _start_uvicorn_thread(host: str, port: int) -> threading.Thread:
    def run() -> None:
        uvicorn.run(app, host=host, port=port, log_level="info")

    thread = threading.Thread(target=run, daemon=True, name="uvicorn-server")
    thread.start()
    return thread


def _wait_for_http_ready(host: str, port: int, timeout: float = 10.0) -> bool:
    import socket

    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            with socket.create_connection((host, port), timeout=1):
                return True
        except OSError:
            time.sleep(0.2)
    return False


def _print_summary(host: str, port: int) -> None:
    print("\n================ Services Summary ================")
    print(f"HTTP server: http://{host}:{port} (FastAPI/uvicorn)")
    print("Local queue: in-memory (endpoint: /local/queue/html)")
    print(f"Worker: in-process background thread (writing to {local_queue_extension.jobs_dir.resolve()})")
    print("Note: This setup is single-host, ephemeral and intended for easy testing.")
    print("For production use a persistent queue (Redis/RQ) and durable storage (S3, DB).")
    print("===================================================\n")


def _job_handler(job: dict) -> dict:
    html = job.get("html", "")
    requests = parse_html_to_docs_sync(html)
    return {"requests": requests}


def main() -> None:
    """Entry point used by run_all.py."""
    host, port = _get_host_port()

    worker = BackgroundWorkerController(local_queue_extension, handler=_job_handler)
    worker.start()
    _start_uvicorn_thread(host, port)

    print("Starting HTTP server and worker...")
    if not _wait_for_http_ready(host, port):
        print("ERROR: HTTP server did not start within timeout")
        return

    _print_summary(host, port)
    print_documentation()
    print("\nRun the process in the foreground to keep services running. Ctrl+C to stop.")

    try:
        while True:
            time.sleep(3600)
    except KeyboardInterrupt:
        print("Shutting down...")
        worker.stop()


__all__ = ["main"]
