"""Unified entry point for the Cobalt tool with graceful fallbacks."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Optional

from app.services.cobalt_local_service import LocalCobaltService, create_local_cobalt_service
from app.services.cobalt_service import CobaltBinaryResult, CobaltError, CobaltService
from app.services.yt_dlp_service import yt_dlp_service
from app.utils.logger import logger


@dataclass
class CobaltProcessResult:
    """Result returned by :class:`CobaltGateway` after processing a request."""

    payload: Dict[str, object]
    binary: Optional[CobaltBinaryResult]
    used_local_fallback: bool
    source_label: str


class CobaltGateway:
    """Try a remote Cobalt instance and fall back to local yt-dlp when required."""

    def __init__(
        self,
        *,
        remote: CobaltService | None,
        local: LocalCobaltService | None,
    ) -> None:
        if not remote and not local:
            raise CobaltError("Neither a remote Cobalt endpoint nor a local fallback is available")

        self._remote = remote
        self._local = local

    @property
    def has_remote(self) -> bool:
        return self._remote is not None

    @property
    def has_local(self) -> bool:
        return self._local is not None

    async def process(
        self,
        payload: Dict[str, object],
        *,
        expect_binary: bool,
        filename_override: Optional[str] = None,
    ) -> CobaltProcessResult:
        """Process a request using the best available backend."""

        last_error: CobaltError | None = None

        if self._remote:
            try:
                data = await self._remote.process(payload)  # type: ignore[arg-type]
                binary: Optional[CobaltBinaryResult] = None
                if expect_binary:
                    binary = await self._remote.download_binary(
                        data,
                        filename_override=filename_override,
                    )

                return CobaltProcessResult(
                    payload=data,
                    binary=binary,
                    used_local_fallback=False,
                    source_label=self._remote.endpoint,
                )
            except CobaltError as exc:
                logger.warning("Remote Cobalt failed (%s). Falling back to local mode if possible.", exc)
                last_error = exc

        if self._local:
            local_result = await self._local.process(
                payload,  # type: ignore[arg-type]
                expect_binary=expect_binary,
                filename_override=filename_override,
            )
            return CobaltProcessResult(
                payload=local_result.payload,
                binary=local_result.binary,
                used_local_fallback=True,
                source_label="local yt-dlp",
            )

        assert last_error is not None
        raise last_error


def create_gateway(
    *,
    remote_base_url: str,
    auth_scheme: str,
    auth_token: str,
    timeout: float,
) -> CobaltGateway:
    """Factory helper that builds a :class:`CobaltGateway` with fallbacks."""

    remote: CobaltService | None = None
    if remote_base_url:
        remote = CobaltService(
            base_url=remote_base_url,
            auth_scheme=auth_scheme or None,
            auth_token=auth_token or None,
            timeout=timeout,
        )

    local = create_local_cobalt_service(yt_dlp_service)

    return CobaltGateway(remote=remote, local=local)
__all__ = ["CobaltGateway", "CobaltProcessResult", "create_gateway"]
