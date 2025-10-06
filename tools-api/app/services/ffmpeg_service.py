"""Utilities for interacting with the system FFmpeg binary."""
from __future__ import annotations

import mimetypes
import re
import shutil
import subprocess
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path
from threading import Lock
from typing import Iterable, Tuple

from fastapi import UploadFile

FORMAT_LINE_PATTERN = re.compile(r"^\s*([D\.])([E\.])\s+([^\s]+)")
_CACHE_TTL_SECONDS = 60 * 60  # one hour


class FfmpegServiceError(RuntimeError):
    """Raised when FFmpeg operations fail or are unavailable."""


@dataclass(frozen=True)
class ConversionResult:
    """Represents a successful FFmpeg conversion."""

    output_path: Path
    filename: str
    media_type: str
    workdir: Path


class FfmpegService:
    """Lightweight wrapper around the FFmpeg CLI for conversions."""

    def __init__(self) -> None:
        self._cache_lock = Lock()
        self._cached_formats: Tuple[float, dict[str, list[str]]] | None = None

    def list_formats(self) -> dict[str, list[str]]:
        """Return supported FFmpeg demuxer/muxer formats with caching."""

        with self._cache_lock:
            if self._cached_formats is not None:
                cached_at, payload = self._cached_formats
                if time.monotonic() - cached_at < _CACHE_TTL_SECONDS:
                    return {key: value.copy() for key, value in payload.items()}

        formats = self._probe_formats()
        with self._cache_lock:
            self._cached_formats = (time.monotonic(), formats)
        return {key: value.copy() for key, value in formats.items()}

    def _probe_formats(self) -> dict[str, list[str]]:
        try:
            completed = subprocess.run(
                ["ffmpeg", "-hide_banner", "-formats"],
                check=True,
                capture_output=True,
                text=True,
            )
        except FileNotFoundError as exc:  # pragma: no cover - depends on environment
            raise FfmpegServiceError(
                "FFmpeg is not installed or not available on the PATH."
            ) from exc
        except subprocess.CalledProcessError as exc:  # pragma: no cover - hard to trigger
            stderr = (exc.stderr or exc.stdout or "").strip()
            message = stderr or "Unable to query FFmpeg formats."
            raise FfmpegServiceError(message) from exc

        demuxers: set[str] = set()
        muxers: set[str] = set()

        for raw_line in completed.stdout.splitlines():
            match = FORMAT_LINE_PATTERN.match(raw_line)
            if not match:
                continue

            demux_flag, mux_flag, names = match.groups()
            for candidate in self._split_format_names(names):
                if demux_flag == "D":
                    demuxers.add(candidate)
                if mux_flag == "E":
                    muxers.add(candidate)

        return {
            "inputs": sorted(demuxers),
            "outputs": sorted(muxers),
            "common": sorted(demuxers & muxers),
        }

    @staticmethod
    def _split_format_names(value: str) -> Iterable[str]:
        for item in value.split(","):
            cleaned = item.strip().lower()
            if cleaned:
                yield cleaned

    def convert_upload(
        self,
        upload: UploadFile,
        *,
        source_format: str | None,
        target_format: str,
    ) -> ConversionResult:
        if not target_format:
            raise FfmpegServiceError("target_format is required")

        available = self.list_formats()
        normalised_target = self._normalise_format(target_format)
        if normalised_target not in {fmt.lower() for fmt in available["outputs"]}:
            raise FfmpegServiceError(
                f"FFmpeg does not support exporting to '{target_format}'."
            )

        normalised_source = None
        if source_format:
            normalised_source = self._normalise_format(source_format)
            if normalised_source not in {fmt.lower() for fmt in available["inputs"]}:
                raise FfmpegServiceError(
                    f"FFmpeg cannot ingest files tagged as '{source_format}'."
                )

        workdir = Path(tempfile.mkdtemp(prefix="ffmpeg-convert-"))
        input_path = self._write_upload(upload, workdir, normalised_source)
        output_filename = self._build_output_filename(upload.filename, normalised_target)
        output_path = workdir / output_filename

        command = [
            "ffmpeg",
            "-hide_banner",
            "-loglevel",
            "error",
            "-y",
        ]
        if normalised_source:
            command.extend(["-f", normalised_source])
        command.extend(["-i", str(input_path), str(output_path)])

        try:
            subprocess.run(command, check=True)
        except FileNotFoundError as exc:  # pragma: no cover - depends on environment
            raise FfmpegServiceError(
                "FFmpeg is not installed or not available on the PATH."
            ) from exc
        except subprocess.CalledProcessError as exc:
            stderr = (exc.stderr or exc.stdout or "").strip()
            message = stderr or "FFmpeg failed to convert the media file."
            raise FfmpegServiceError(message) from exc

        if not output_path.exists():  # pragma: no cover - defensive
            raise FfmpegServiceError("FFmpeg reported success but no output file was created.")

        mime_type, _ = mimetypes.guess_type(output_filename)
        media_type = mime_type or "application/octet-stream"
        return ConversionResult(output_path=output_path, filename=output_filename, media_type=media_type, workdir=workdir)

    def cleanup_directory(self, directory: Path | str | None) -> None:
        if not directory:
            return
        try:
            shutil.rmtree(directory, ignore_errors=True)
        except OSError:  # pragma: no cover - ignore cleanup errors
            pass

    @staticmethod
    def _normalise_format(value: str) -> str:
        cleaned = value.strip().lower().lstrip(".")
        if not cleaned:
            raise FfmpegServiceError("Format names must contain letters or numbers.")
        if not re.fullmatch(r"[a-z0-9_]+", cleaned):
            raise FfmpegServiceError(
                "Format names may only include letters, numbers, or underscores."
            )
        return cleaned

    @staticmethod
    def _write_upload(upload: UploadFile, workdir: Path, source_format: str | None) -> Path:
        stem = "source"
        suffix = ""
        if upload.filename:
            original = Path(upload.filename)
            if original.suffix:
                suffix = original.suffix
            else:
                stem = original.stem or stem
        if not suffix and source_format:
            suffix = f".{source_format}"
        if not suffix:
            suffix = ".bin"

        destination = workdir / f"{stem}{suffix}"
        upload.file.seek(0)
        with destination.open("wb") as buffer:
            shutil.copyfileobj(upload.file, buffer)
        return destination

    @staticmethod
    def _build_output_filename(original_name: str | None, target_format: str) -> str:
        candidate = "converted"
        if original_name:
            stem = Path(original_name).stem.strip()
            if stem:
                candidate = stem
        return f"{candidate}.{target_format}"


ffmpeg_service = FfmpegService()
