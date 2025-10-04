"""Client helpers for integrating with a Cobalt media downloader instance."""
from __future__ import annotations

import base64
import json
from dataclasses import dataclass
from typing import Any, Dict, Optional

import httpx

from app.utils.logger import logger


class CobaltError(RuntimeError):
    """Raised when communication with a Cobalt instance fails."""


@dataclass
class CobaltBinaryResult:
    """Binary download returned by the Cobalt service."""

    content: bytes
    filename: str
    content_type: str
    metadata: Dict[str, Any]
    encoded_metadata: str


class CobaltService:
    """Thin wrapper around the Cobalt HTTP API."""

    def __init__(
        self,
        *,
        base_url: str,
        auth_scheme: Optional[str] = None,
        auth_token: Optional[str] = None,
        timeout: Optional[float] = 60.0,
    ) -> None:
        if not base_url:
            raise CobaltError("Cobalt API base URL is not configured")

        self.endpoint = base_url.strip()
        self.auth_scheme = auth_scheme or ""
        self.auth_token = auth_token or ""
        self.timeout = timeout

    def _headers(self) -> Dict[str, str]:
        headers = {
            "Accept": "application/json",
            "Content-Type": "application/json",
        }

        if self.auth_scheme and self.auth_token:
            headers["Authorization"] = f"{self.auth_scheme} {self.auth_token}"

        return headers

    async def process(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """Submit a media request to the configured Cobalt instance."""

        logger.info("Submitting request to Cobalt at %s", self.endpoint)

        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.post(self.endpoint, json=payload, headers=self._headers())
                response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            detail = exc.response.text
            logger.error("Cobalt request failed with status %s: %s", exc.response.status_code, detail)
            raise CobaltError("Cobalt instance rejected the request") from exc
        except httpx.HTTPError as exc:  # pragma: no cover - network errors bubble up
            logger.error("Unable to reach Cobalt instance: %s", exc)
            raise CobaltError("Unable to reach Cobalt instance") from exc

        try:
            data = response.json()
        except json.JSONDecodeError as exc:
            logger.error("Cobalt response was not valid JSON: %s", response.text[:200])
            raise CobaltError("Cobalt response was not valid JSON") from exc

        return data

    async def download_binary(
        self,
        result: Dict[str, Any],
        *,
        filename_override: Optional[str] = None,
    ) -> CobaltBinaryResult:
        """Download the media referenced by a Cobalt `tunnel` or `redirect` response."""

        status = result.get("status")
        if status not in {"tunnel", "redirect"}:
            raise CobaltError("Cobalt response does not contain a downloadable file")

        download_url = result.get("url")
        if not download_url:
            raise CobaltError("Cobalt response is missing a download URL")

        filename = filename_override or result.get("filename") or "cobalt-download.bin"

        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.get(download_url)
                response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            logger.error("Cobalt download failed (%s): %s", exc.response.status_code, exc.response.text[:200])
            raise CobaltError("Unable to download media from Cobalt") from exc
        except httpx.HTTPError as exc:  # pragma: no cover - network errors bubble up
            logger.error("Cobalt download encountered a network error: %s", exc)
            raise CobaltError("Unable to download media from Cobalt") from exc

        content_type = response.headers.get("content-type", "application/octet-stream")

        metadata = dict(result)
        metadata.setdefault("downloadUrl", download_url)

        encoded_metadata = base64.b64encode(json.dumps(metadata, ensure_ascii=False).encode("utf-8")).decode("utf-8")

        return CobaltBinaryResult(
            content=response.content,
            filename=filename,
            content_type=content_type,
            metadata=metadata,
            encoded_metadata=encoded_metadata,
        )
