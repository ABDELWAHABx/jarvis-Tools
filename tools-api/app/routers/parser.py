from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from app.services.parser_service import (
    parse_html,
    parse_markdown,
    parse_html_to_docs_sync,
    parse_markdown_to_docs_sync,
)
from app.utils.logger import logger
from app.services import queue as rq_queue
from rq.job import Job
from redis import Redis
import os

router = APIRouter()


class HTMLParseRequest(BaseModel):
    html: str


class MarkdownParseRequest(BaseModel):
    markdown: str


class EnqueueResponse(BaseModel):
    job_id: str


@router.post("/html")
async def parse_html_endpoint(request: HTMLParseRequest):
    try:
        result = await parse_html(request.html)
        return {"requests": result}
    except Exception as e:
        logger.error(f"HTML parse error: {e}")
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/markdown")
async def parse_markdown_endpoint(request: MarkdownParseRequest):
    try:
        result = await parse_markdown(request.markdown)
        return {"requests": result}
    except Exception as e:
        logger.error(f"Markdown parse error: {e}")
        raise HTTPException(status_code=400, detail=str(e))


# Queue endpoints: enqueue jobs for background processing and create Google Docs requests
@router.post("/queue/html", response_model=EnqueueResponse)
def enqueue_html(request: HTMLParseRequest):
    try:
        job = rq_queue.enqueue(parse_html_to_docs_sync, request.html)
        return {"job_id": job.id}
    except Exception as e:
        logger.error(f"Enqueue HTML error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/queue/markdown", response_model=EnqueueResponse)
def enqueue_markdown(request: MarkdownParseRequest):
    try:
        job = rq_queue.enqueue(parse_markdown_to_docs_sync, request.markdown)
        return {"job_id": job.id}
    except Exception as e:
        logger.error(f"Enqueue Markdown error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/job/{job_id}")
def job_status(job_id: str):
    try:
        redis_url = os.getenv("REDIS_URL", "redis://localhost:6379/0")
        redis_conn = Redis.from_url(redis_url)
        job = Job.fetch(job_id, connection=redis_conn)
        if job.is_finished:
            return {"status": "finished", "result": job.result}
        elif job.is_queued:
            return {"status": "queued"}
        elif job.is_started:
            return {"status": "started"}
        elif job.is_failed:
            return {"status": "failed", "error": str(job.exc_info)}
        else:
            return {"status": "unknown"}
    except Exception as e:
        logger.error(f"Job status error: {e}")
        raise HTTPException(status_code=404, detail=str(e))
