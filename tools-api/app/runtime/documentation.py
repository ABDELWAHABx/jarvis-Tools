"""Utility helpers for displaying Tools API documentation snippets."""
from __future__ import annotations

import json
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, AsyncIterator, Dict, Iterable, Iterator, List, Optional, Tuple

from fastapi import FastAPI

try:  # pragma: no cover - guarded import for environments without PyYAML
    import yaml
except Exception:  # pragma: no cover - fallback if PyYAML is missing
    yaml = None  # type: ignore


CATALOG_PATH = Path(__file__).resolve().parents[2] / "docs" / "service_catalog.yaml"


def _pretty_json(data: Any) -> str:
    """Return JSON formatted text for examples."""

    if data is None:
        return "null"
    return json.dumps(data, indent=2, sort_keys=True, ensure_ascii=False)


def _load_catalog() -> Dict[str, Any]:
    """Load the service catalog YAML (or JSON) file into a dictionary."""

    if not CATALOG_PATH.exists():
        return {
            "error": f"Service catalog not found at {CATALOG_PATH}. Create the file or update code_flow.md instructions.",
        }

    try:
        contents = CATALOG_PATH.read_text(encoding="utf-8")
        if yaml is not None:
            try:
                catalog = yaml.safe_load(contents)
            except Exception:  # pragma: no cover - fall back to JSON parsing
                catalog = None
        else:
            catalog = None

        if catalog is None:
            try:
                catalog = json.loads(contents)
            except json.JSONDecodeError as exc:
                return {"error": f"Failed to parse service catalog: {exc}"}
    except Exception as exc:  # pragma: no cover - defensive logging
        return {"error": f"Failed to read service catalog: {exc}"}

    if not isinstance(catalog, dict):
        return {"error": "Service catalog must be a mapping with a 'services' key."}
    return catalog


def _normalize_io_spec(spec: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    if not isinstance(spec, dict):
        return {}
    normalized: Dict[str, Any] = {
        "content_type": spec.get("content_type"),
        "model": spec.get("model"),
    }
    fields = spec.get("fields")
    if isinstance(fields, dict):
        normalized["fields"] = dict(fields)
    else:
        normalized["fields"] = {}
    example = spec.get("example")
    if example is not None:
        normalized["example"] = example
    return normalized


def _normalize_endpoint(endpoint: Dict[str, Any]) -> Dict[str, Any]:
    method = str(endpoint.get("method", "GET")).upper()
    path = str(endpoint.get("path", "/"))
    headline = endpoint.get("headline")
    tagline = endpoint.get("tagline")
    description = endpoint.get("description")

    normalized = {
        "method": method,
        "path": path,
        "headline": headline or f"{method} {path}",
        "tagline": tagline or description,
        "description": description,
        "request": _normalize_io_spec(endpoint.get("request")),
        "response": _normalize_io_spec(endpoint.get("response")),
        "notes": list(endpoint.get("notes", [])) if isinstance(endpoint.get("notes"), list) else [],
    }
    return normalized


def _catalog_services() -> Tuple[List[Dict[str, Any]], Optional[str]]:
    catalog = _load_catalog()
    error = catalog.get("error") if isinstance(catalog, dict) else None
    if error:
        return [], str(error)

    services_raw = catalog.get("services") if isinstance(catalog, dict) else None
    if not services_raw:
        return [], "No services defined. Update docs/service_catalog.yaml to document the API surface."

    services: List[Dict[str, Any]] = []
    for service in services_raw:
        if not isinstance(service, dict):
            continue
        entry = {
            "name": service.get("name", "Unnamed Service"),
            "summary": service.get("summary"),
            "docs_url": service.get("docs_url"),
            "endpoints": [],
        }
        endpoints = service.get("endpoints", [])
        if isinstance(endpoints, list):
            entry["endpoints"] = [_normalize_endpoint(ep) for ep in endpoints if isinstance(ep, dict)]
        services.append(entry)

    return services, None


def _fields_as_sentences(fields: Optional[Dict[str, str]]) -> List[str]:
    if not isinstance(fields, dict) or not fields:
        return []
    sentences: List[str] = []
    for name, description in fields.items():
        desc = str(description).strip()
        if not desc:
            desc = "No description provided."
        if not desc.endswith(('.', '!', '?')):
            desc = f"{desc}."
        sentences.append(f"{name}: {desc}")
    return sentences


def _documentation_lines() -> Iterable[str]:
    """Yield formatted lines that describe the public API surface in natural language."""

    services, error = _catalog_services()

    yield "\nTools API — Service Catalog"
    yield "=" * 60
    yield ""

    if error:
        yield f"⚠️  {error}"
        yield "Update docs/service_catalog.yaml to finish documenting the tools."
        yield "=" * 60
        return

    for index, service in enumerate(services, start=1):
        yield f"{index}. {service['name']}"
        summary = service.get("summary")
        if summary:
            yield f"   {summary}"
        docs_url = service.get("docs_url")
        if docs_url:
            yield f"   Interactive docs: {docs_url}"

        endpoints: List[Dict[str, Any]] = service.get("endpoints", [])
        if endpoints:
            yield "   Tools:"
        for endpoint in endpoints:
            yield f"     • {endpoint['headline']}"
            tagline = endpoint.get("tagline")
            if tagline:
                yield f"       {tagline}"
            yield f"       Call: {endpoint['method']} {endpoint['path']}"
            content_type = endpoint.get("request", {}).get("content_type")
            if content_type:
                yield f"       Content-Type: {content_type}"

            request_fields = _fields_as_sentences(endpoint.get("request", {}).get("fields"))
            if request_fields:
                yield "       Send:"
                for field in request_fields:
                    yield f"         - {field}"
            else:
                yield "       Send: No request body documented."

            response_fields = _fields_as_sentences(endpoint.get("response", {}).get("fields"))
            if response_fields:
                yield "       Receive:"
                for field in response_fields:
                    yield f"         - {field}"
            else:
                yield "       Receive: No response body documented."

            for note in endpoint.get("notes", []):
                yield f"       Note: {note}"

            example = endpoint.get("request", {}).get("example")
            if example is not None:
                yield "       Example request:"
                for line in _pretty_json(example).splitlines():
                    yield f"         {line}"
            response_example = endpoint.get("response", {}).get("example")
            if response_example is not None:
                yield "       Example response:"
                for line in _pretty_json(response_example).splitlines():
                    yield f"         {line}"

        if index < len(services):
            yield ""

    yield ""
    yield "Health check: http://localhost:8000/health"
    yield "Interactive documentation: http://localhost:8000/docs"
    yield "=" * 60


def render_documentation() -> str:
    """Return the documentation banner as a single string."""

    return "\n".join(_documentation_lines())


def render_request_overview(host: str, port: int) -> str:
    """Return a concise overview highlighting endpoints and their inputs."""

    base_url = f"http://{host}:{port}"
    lines: List[str] = [
        "",
        "Tools API — Quickstart",
        "=" * 45,
        f"Base URL: {base_url}",
        "",
        "What you can do right now:",
    ]

    services, error = _catalog_services()

    if error:
        lines.append("")
        lines.append(f"⚠️  {error}")
        lines.append("Review docs/service_catalog.yaml to fill in the natural language descriptions.")
        lines.append("")
        lines.append(f"Swagger UI: {base_url}/docs")
        lines.append(f"Health check: {base_url}/health")
        lines.append("")
        lines.append("Press Ctrl+C to stop the server.")
        return "\n".join(lines)

    for service in services:
        service_name = service.get("name", "Service")
        lines.append("")
        lines.append(service_name)
        summary = service.get("summary")
        if summary:
            lines.append(f"  {summary}")

        for endpoint in service.get("endpoints", []):
            descriptor = f"  • {endpoint['headline']} — {endpoint['method']} {endpoint['path']}"
            content_type = endpoint.get("request", {}).get("content_type")
            if content_type:
                descriptor += f" ({content_type})"
            lines.append(descriptor)

            tagline = endpoint.get("tagline")
            if tagline:
                lines.append(f"    {tagline}")

            request_fields = _fields_as_sentences(endpoint.get("request", {}).get("fields"))
            if request_fields:
                lines.append("    Send:")
                for field in request_fields:
                    lines.append(f"      - {field}")
            else:
                lines.append("    Send: No request body documented.")

            response_fields = _fields_as_sentences(endpoint.get("response", {}).get("fields"))
            if response_fields:
                lines.append("    Receive:")
                for field in response_fields:
                    lines.append(f"      - {field}")
            else:
                lines.append("    Receive: No structured response documented.")

    lines.append("")
    lines.append(f"Swagger UI: {base_url}/docs")
    lines.append(f"Health check: {base_url}/health")
    lines.append("")
    lines.append("Press Ctrl+C to stop the server.")
    return "\n".join(lines)


def get_service_details() -> Tuple[List[Dict[str, Any]], Optional[str]]:
    """Expose normalized service definitions for UI surfaces."""

    return _catalog_services()


def print_documentation() -> None:
    """Print the documentation banner to stdout."""

    print(render_documentation())


@asynccontextmanager
async def documentation_lifespan(app: FastAPI) -> AsyncIterator[None]:
    """FastAPI lifespan hook that prints the documentation banner."""

    print_documentation()
    yield
