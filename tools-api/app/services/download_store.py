"""Lightweight on-disk storage for generated media downloads."""
from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict
from uuid import uuid4

from app.utils.logger import logger


@dataclass
class StoredDownload:
    """Metadata describing a file persisted by :class:`DownloadStore`."""

    file_id: str
    path: Path
    filename: str
    content_type: str
    metadata: Dict[str, Any]


class DownloadStore:
    """Persist yt-dlp downloads so they can be fetched via stable URLs."""

    def __init__(self, root: Path | None = None) -> None:
        base_path = root or self._default_root()
        self.root = base_path
        self.root.mkdir(parents=True, exist_ok=True)

    @staticmethod
    def _default_root() -> Path:
        """Resolve the default storage path inside the application directory."""

        base_env = os.getenv("MEDIA_DOWNLOAD_DIR")
        if base_env:
            candidate = Path(base_env).expanduser()
            return candidate

        return Path(__file__).resolve().parents[1] / "downloads"

    def store(self, *, filename: str, content: bytes, content_type: str, metadata: Dict[str, Any]) -> StoredDownload:
        """Persist a binary payload and return the structured descriptor."""

        file_id = uuid4().hex
        target_dir = self.root / file_id
        target_dir.mkdir(parents=True, exist_ok=False)

        safe_name = Path(filename).name or "download.bin"
        file_path = target_dir / safe_name
        file_path.write_bytes(content)

        metadata_path = target_dir / "metadata.json"
        metadata_payload = json.dumps(metadata, ensure_ascii=False, default=str)
        metadata_path.write_text(metadata_payload, encoding="utf-8")

        logger.debug("Stored download %s at %s", file_id, file_path)

        return StoredDownload(
            file_id=file_id,
            path=file_path,
            filename=safe_name,
            content_type=content_type or "application/octet-stream",
            metadata=metadata,
        )

    def retrieve(self, file_id: str) -> StoredDownload:
        """Load a stored download descriptor or raise :class:`FileNotFoundError`."""

        target_dir = self.root / file_id
        if not target_dir.exists() or not target_dir.is_dir():
            raise FileNotFoundError(f"Download {file_id!r} not found")

        files = [path for path in target_dir.iterdir() if path.is_file() and path.name != "metadata.json"]
        if not files:
            raise FileNotFoundError(f"Download {file_id!r} is missing content")

        file_path = files[0]
        metadata_path = target_dir / "metadata.json"
        metadata: Dict[str, Any] = {}
        if metadata_path.exists():
            try:
                metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                logger.warning("Metadata for %s is not valid JSON", file_id)

        content_type = metadata.get("content_type") or "application/octet-stream"
        original_name = metadata.get("filename") or file_path.name

        return StoredDownload(
            file_id=file_id,
            path=file_path,
            filename=original_name,
            content_type=content_type,
            metadata=metadata,
        )


download_store = DownloadStore()

__all__ = ["download_store", "DownloadStore", "StoredDownload"]

