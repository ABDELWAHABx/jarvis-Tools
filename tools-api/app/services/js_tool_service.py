"""Utilities for bridging FastAPI endpoints to JavaScript-powered tools."""
from __future__ import annotations

import base64
import json
import re
import shutil
import subprocess
import tempfile
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional
import zipfile

from app.utils.logger import logger


class JavaScriptToolError(RuntimeError):
    """Raised when a JavaScript-backed tool fails to execute."""


@dataclass
class PanosplitterResult:
    """Structured result returned from the Node.js panosplitter CLI."""

    mode: str
    slice_count: int
    slice_width: int
    slice_height: int
    scaled_width: int
    scaled_height: int
    slices: List[Dict[str, int]]
    full_view: Dict[str, int]


NODE_EXECUTABLE = shutil.which("node")
NPM_EXECUTABLE = shutil.which("npm")


def _ensure_node_available() -> None:
    """Verify that the runtime has Node.js installed."""

    if NODE_EXECUTABLE is None:
        raise JavaScriptToolError(
            "Node.js is required to execute JavaScript tools. Install Node.js and ensure "
            "the `node` binary is available on PATH."
        )

    if NPM_EXECUTABLE is None:
        raise JavaScriptToolError(
            "npm is required to install JavaScript tool dependencies. Install Node.js/npm and "
            "ensure the `npm` binary is available on PATH."
        )


def _ensure_dependencies(tool_dir: Path) -> None:
    """Install npm dependencies for the JavaScript tool if necessary."""

    node_modules = tool_dir / "node_modules"
    package_json = tool_dir / "package.json"

    if not package_json.exists():
        raise JavaScriptToolError(f"Missing package.json in {tool_dir}")

    # Install dependencies when node_modules is missing. The call is idempotent because npm skips reinstall
    # when modules are already present.
    if not node_modules.exists():
        logger.info("Installing npm dependencies for %s", tool_dir)
        result = subprocess.run(
            [NPM_EXECUTABLE, "install"],
            cwd=str(tool_dir),
            capture_output=True,
            text=True,
            check=False,
        )
        if result.returncode != 0:
            logger.error("npm install failed: %s", result.stderr)
            raise JavaScriptToolError("Failed to install JavaScript tool dependencies")


def _parse_cli_output(stdout: str) -> PanosplitterResult:
    """Parse the JSON payload emitted by the Node.js CLI."""

    stdout = stdout.strip()
    if not stdout:
        raise JavaScriptToolError("JavaScript tool returned no output")

    # Some CLIs might emit multiple lines. The JSON payload is expected to be on the last line.
    json_payload = stdout.splitlines()[-1]

    try:
        payload = json.loads(json_payload)
    except json.JSONDecodeError as exc:
        raise JavaScriptToolError("Unable to decode JavaScript tool output as JSON") from exc

    if "error" in payload:
        raise JavaScriptToolError(payload["error"])

    try:
        return PanosplitterResult(
            mode=payload["mode"],
            slice_count=int(payload["sliceCount"]),
            slice_width=int(payload["sliceWidth"]),
            slice_height=int(payload["sliceHeight"]),
            scaled_width=int(payload["scaledWidth"]),
            scaled_height=int(payload["scaledHeight"]),
            slices=list(payload["slices"]),
            full_view=dict(payload["fullView"]),
        )
    except (KeyError, TypeError, ValueError) as exc:
        raise JavaScriptToolError("JavaScript tool response was missing required fields") from exc


def _invoke_panosplitter_cli(
    cli_path: Path,
    input_path: Path,
    output_dir: Path,
    mode: str,
    timeout: Optional[int] = 120,
) -> PanosplitterResult:
    """Run the Node.js CLI and return the parsed response."""

    command = [
        NODE_EXECUTABLE,
        str(cli_path),
        "--input",
        str(input_path),
        "--output",
        str(output_dir),
        "--mode",
        mode,
    ]

    logger.debug("Running panosplitter CLI: %s", " ".join(command))
    result = subprocess.run(
        command,
        cwd=str(cli_path.parent),
        capture_output=True,
        text=True,
        timeout=timeout,
        check=False,
    )

    if result.returncode != 0:
        logger.error("JavaScript tool failed: %s", result.stderr)
        raise JavaScriptToolError("Panosplitter CLI execution failed")

    return _parse_cli_output(result.stdout)


def _encode_file(path: Path) -> Dict[str, str]:
    """Base64 encode a file for transport over HTTP."""

    data = base64.b64encode(path.read_bytes()).decode("utf-8")
    return {
        "filename": path.name,
        "content_type": "image/jpeg",
        "base64": data,
    }


def _create_zip_payload(
    directory: Path,
    manifest: Dict[str, Any],
    zip_name: str = "panosplitter_slices.zip",
) -> Dict[str, str]:
    """Bundle the generated assets into a base64-encoded zip file."""

    with tempfile.NamedTemporaryFile(suffix=".zip", delete=False) as tmp_file:
        tmp_path = Path(tmp_file.name)

    try:
        with zipfile.ZipFile(tmp_path, "w", compression=zipfile.ZIP_DEFLATED) as zip_file:
            for file_path in sorted(directory.glob("*.jpg")):
                zip_file.write(file_path, arcname=file_path.name)

            zip_file.writestr(
                "manifest.json",
                json.dumps(manifest, indent=2, ensure_ascii=False),
            )

        zip_data = base64.b64encode(tmp_path.read_bytes()).decode("utf-8")
        return {
            "filename": zip_name,
            "base64": zip_data,
            "content_type": "application/zip",
        }
    finally:
        if tmp_path.exists():
            tmp_path.unlink()


def _sanitize_filename(filename: Optional[str]) -> str:
    """Sanitize an untrusted filename supplied by the client.

    - Strips any directory components by taking the basename.
    - Replaces unsafe characters with underscores.
    - Removes leading dots to avoid hidden/traversal names.
    - Ensures a safe image extension (defaults to .jpg).
    - Falls back to a generated name when necessary.
    """
    # If no filename provided, generate a unique one
    if not filename:
        return f"upload_{uuid.uuid4().hex}.jpg"

    # Take basename to remove any path components
    base = Path(filename).name

    # Remove leading dots (e.g. ".bashrc" or "..")
    base = base.lstrip(".")

    # Split name and extension
    name = Path(base).stem
    ext = Path(base).suffix.lower()

    # Replace any character that isn't alphanumeric, dot, underscore or dash
    name = re.sub(r"[^A-Za-z0-9._-]", "_", name)

    if not name:
        name = uuid.uuid4().hex

    # Allow only a small set of image extensions; default to .jpg otherwise
    if ext not in (".jpg", ".jpeg", ".png", ".webp", ".gif"):
        ext = ".jpg"

    safe = f"{name}{ext}"

    # Enforce a maximum filename length to avoid surprises
    if len(safe) > 255:
        safe = safe[:255]

    return safe


def run_panosplitter(
    image_bytes: bytes,
    *,
    high_res: bool = False,
    filename: Optional[str] = None,
    timeout: Optional[int] = 120,
) -> Dict[str, object]:
    """Execute the JavaScript panorama splitter and return assets + metadata."""

    _ensure_node_available()

    tool_dir = Path(__file__).resolve().parents[2] / "js_tools" / "panosplitter"
    cli_path = tool_dir / "cli.js"
    if not cli_path.exists():
        raise JavaScriptToolError("Panosplitter CLI script not found")

    _ensure_dependencies(tool_dir)

    mode = "highres" if high_res else "standard"
    # Treat client-supplied filename as untrusted and sanitize it before use.
    filename = _sanitize_filename(filename)

    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp_dir_path = Path(tmp_dir)
        input_path = tmp_dir_path / filename
        output_dir = tmp_dir_path / "output"
        output_dir.mkdir(parents=True, exist_ok=True)

        input_path.write_bytes(image_bytes)

        result = _invoke_panosplitter_cli(cli_path, input_path, output_dir, mode, timeout=timeout)

        slices_payload = []
        manifest_slices: List[Dict[str, Any]] = []
        for slice_info in result.slices:
            file_path = output_dir / slice_info["filename"]
            if not file_path.exists():
                raise JavaScriptToolError(f"Expected slice not found: {file_path.name}")
            encoded = _encode_file(file_path)
            encoded.update({
                "width": slice_info.get("width"),
                "height": slice_info.get("height"),
            })
            slices_payload.append(encoded)

            manifest_slices.append(
                {
                    "filename": file_path.name,
                    "width": slice_info.get("width"),
                    "height": slice_info.get("height"),
                    "content_type": encoded["content_type"],
                }
            )

        full_view_path = output_dir / result.full_view["filename"]
        if not full_view_path.exists():
            raise JavaScriptToolError("Full view image was not generated by the JavaScript tool")

        full_view_payload = _encode_file(full_view_path)
        full_view_payload.update({
            "width": result.full_view.get("width"),
            "height": result.full_view.get("height"),
        })

        manifest_full_view = {
            "filename": full_view_path.name,
            "width": full_view_payload.get("width"),
            "height": full_view_payload.get("height"),
            "content_type": full_view_payload["content_type"],
        }

        metadata = {
            "mode": result.mode,
            "slice_count": result.slice_count,
            "slice_width": result.slice_width,
            "slice_height": result.slice_height,
            "scaled_width": result.scaled_width,
            "scaled_height": result.scaled_height,
            "original_filename": filename,
        }

        manifest = {
            "metadata": metadata,
            "slices": manifest_slices,
            "full_view": manifest_full_view,
        }

        zip_payload = _create_zip_payload(output_dir, manifest)

        return {
            "metadata": metadata,
            "zip_file": zip_payload,
            "slices": slices_payload,
            "full_view": full_view_payload,
            "manifest": manifest,
        }
