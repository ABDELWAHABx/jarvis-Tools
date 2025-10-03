"""Utility helpers for displaying Tools API documentation snippets."""
from __future__ import annotations

import json
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, AsyncIterator, Dict, Iterable, Iterator, List, Optional

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
    """Load the service catalog YAML file into a dictionary."""

    if yaml is None:
        return {
            "error": "PyYAML is not installed. Install it or update requirements.txt to enable the service catalog printer.",
        }

    if not CATALOG_PATH.exists():
        return {
            "error": f"Service catalog not found at {CATALOG_PATH}. Create the file or update code_flow.md instructions.",
        }

    try:
        contents = CATALOG_PATH.read_text(encoding="utf-8")
        catalog = yaml.safe_load(contents)
    except Exception as exc:  # pragma: no cover - defensive logging
        return {"error": f"Failed to parse service catalog: {exc}"}

    if not isinstance(catalog, dict):
        return {"error": "Service catalog must be a mapping with a 'services' key."}
    return catalog


def _format_fields(fields: Dict[str, str]) -> Iterator[str]:
    for name, description in fields.items():
        yield f"         • {name}: {description}"


def _format_endpoint(endpoint: Dict[str, Any]) -> Iterator[str]:
    method = str(endpoint.get("method", "GET")).upper()
    path = endpoint.get("path", "/")
    description = endpoint.get("description")
    yield f"   {method} {path}"
    if description:
        yield f"      {description}"

    request_spec: Optional[Dict[str, Any]] = endpoint.get("request")
    if request_spec:
        content_type = request_spec.get("content_type")
        model = request_spec.get("model")
        if content_type or model:
            ct = f" ({content_type})" if content_type else ""
            model_text = f" — {model}" if model else ""
            yield f"      Request{ct}{model_text}"
        fields = request_spec.get("fields")
        if isinstance(fields, dict) and fields:
            yield "      Fields:"
            yield from _format_fields(fields)
        example = request_spec.get("example")
        if example is not None:
            yield "      Example Request:"
            for line in _pretty_json(example).splitlines():
                yield f"         {line}"

    response_spec: Optional[Dict[str, Any]] = endpoint.get("response")
    if response_spec:
        content_type = response_spec.get("content_type")
        model = response_spec.get("model")
        if content_type or model:
            ct = f" ({content_type})" if content_type else ""
            model_text = f" — {model}" if model else ""
            yield f"      Response{ct}{model_text}"
        fields = response_spec.get("fields")
        if isinstance(fields, dict) and fields:
            yield "      Fields:"
            yield from _format_fields(fields)
        example = response_spec.get("example")
        if example is not None:
            yield "      Example Response:"
            for line in _pretty_json(example).splitlines():
                yield f"         {line}"

    notes: Optional[List[str]] = endpoint.get("notes")
    if notes:
        yield "      Notes:"
        for note in notes:
            yield f"         - {note}"


def _format_service(service: Dict[str, Any]) -> Iterator[str]:
    name = service.get("name", "Unnamed Service")
    summary = service.get("summary")
    docs_url = service.get("docs_url")

    yield name
    if summary:
        yield f"  {summary}"
    if docs_url:
        yield f"  Docs UI: {docs_url}"

    endpoints = service.get("endpoints", [])
    for endpoint in endpoints:
        yield from _format_endpoint(endpoint)


def _documentation_lines() -> Iterable[str]:
    """Yield formatted lines that describe the public API surface."""

    catalog = _load_catalog()
    error = catalog.get("error") if isinstance(catalog, dict) else None

    yield "\nTools API — Service Catalog"
    yield "=" * 50

    if error:
        yield f"\n⚠️  {error}"
        yield "\nSee docs/service_catalog.yaml for the canonical API list."
        yield "=" * 50
        return

    services = catalog.get("services") if isinstance(catalog, dict) else None
    if not services:
        yield "\nNo services defined. Update docs/service_catalog.yaml to document the API surface."
        yield "=" * 50
        return

    for index, service in enumerate(services, start=1):
        yield ""
        yield from _format_service(service)
        if index < len(services):
            yield ""

    yield ""
    yield "Interactive documentation: http://localhost:8000/docs"
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
