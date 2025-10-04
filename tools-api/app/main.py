from pathlib import Path

from fastapi import FastAPI, Request, status
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.exceptions import RequestValidationError
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from app.routers import docx, gdocs_parser, image_tools, js_tools, media, parser
from app.extensions import local_queue_extension
from app.utils.logger import logger
from app.config import settings
import time


app = FastAPI(
    title="Tools API",
    version="1.0.0",
    description="API for document parsing, DOCX manipulation, and n8n integrations"
)


# Static and template configuration
BASE_DIR = Path(__file__).resolve().parent
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))
static_dir = BASE_DIR / "static"
app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")


# Middleware - CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# Middleware - Request logging for debugging (optional but helpful)
@app.middleware("http")
async def log_requests(request: Request, call_next):
    """Log all incoming requests with timing info."""
    start_time = time.time()
    logger.info(f"→ {request.method} {request.url.path} | Client: {request.client.host}")
    
    # Log content type for file uploads
    if request.headers.get("content-type"):
        logger.debug(f"  Content-Type: {request.headers.get('content-type')}")
    
    response = await call_next(request)
    process_time = time.time() - start_time
    
    logger.info(f"← {request.method} {request.url.path} | Status: {response.status_code} | Time: {process_time:.3f}s")
    return response


# Routers
app.include_router(parser.router, prefix="/parse", tags=["parser"])
app.include_router(docx.router)  # Already has /docx prefix
app.include_router(gdocs_parser.router)
app.include_router(js_tools.router)
app.include_router(media.router)
app.include_router(image_tools.router)
local_queue_extension.register(app)


# Custom exception handler for 422 Validation Errors (crucial for debugging n8n issues)
@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    """
    Catch FastAPI validation errors (422) and return detailed, actionable messages.
    This is especially helpful for debugging multipart/form-data and file upload issues from n8n.
    """
    errors = exc.errors()
    logger.warning(f"Validation error on {request.method} {request.url.path}: {errors}")
    
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content={
            "detail": "Request validation failed. Check field names, types, and Content-Type header.",
            "errors": errors,
            "hint": "For file uploads: ensure Content-Type is 'multipart/form-data' and field name matches endpoint expectation (e.g., 'file')."
        },
    )


# Global exception handler for unexpected errors
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    """Catch all unhandled exceptions and log them."""
    logger.error(f"Unhandled exception on {request.method} {request.url.path}: {type(exc).__name__}: {exc}", exc_info=True)
    return JSONResponse(
        status_code=500, 
        content={
            "detail": "Internal Server Error",
            "error_type": type(exc).__name__,
            "message": str(exc) if settings.DEBUG else "An unexpected error occurred"
        }
    )


# Startup and shutdown events
@app.on_event("startup")
async def startup_event():
    """Run on application startup."""
    logger.info("🚀 Tools API starting up...")
    logger.info(f"Environment: {settings.ENVIRONMENT if hasattr(settings, 'ENVIRONMENT') else 'production'}")
    logger.info(f"CORS enabled for all origins")


@app.on_event("shutdown")
async def shutdown_event():
    """Run on application shutdown."""
    logger.info("🛑 Tools API shutting down...")


# Health check
@app.get("/health", tags=["system"])
async def health():
    """Health check endpoint for monitoring and load balancers."""
    return {
        "status": "ok",
        "service": "Tools API",
        "version": "1.0.0"
    }


# Root HTML studio
@app.get("/", response_class=HTMLResponse, include_in_schema=False)
async def studio(request: Request):
    """Serve the interactive Tools API Studio dashboard."""
    return templates.TemplateResponse(
        "studio.html",
        {
            "request": request,
            "docs_url": app.docs_url or "/docs",
            "openapi_url": app.openapi_url or "/openapi.json",
            "version": app.version or "",
        },
    )


@app.get("/api", tags=["system"])
async def root_metadata():
    """API metadata endpoint kept for backwards compatibility."""
    return {
        "message": "Tools API",
        "version": app.version,
        "docs": app.docs_url,
        "health": "/health",
    }
