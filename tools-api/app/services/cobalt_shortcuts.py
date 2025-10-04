"""Shortcut definitions for common Cobalt download presets."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Iterable, List, Literal


@dataclass(frozen=True)
class CobaltShortcut:
    """Simple descriptor for a canned Cobalt request."""

    slug: str
    label: str
    description: str
    payload: Dict[str, Any]
    response_format: Literal["json", "binary"] = "json"


_SHORTCUTS: List[CobaltShortcut] = [
    CobaltShortcut(
        slug="youtube-audio",
        label="YouTube → MP3",
        description="High bitrate MP3 download tuned for podcasts and music.",
        payload={
            "service": "youtube",
            "downloadMode": "audio",
            "audioFormat": "mp3",
            "audioBitrate": "320",
        },
        response_format="binary",
    ),
    CobaltShortcut(
        slug="youtube-video",
        label="YouTube → 1080p MP4",
        description="Grab a 1080p H.264 MP4 with proxying disabled for speed.",
        payload={
            "service": "youtube",
            "videoQuality": "1080",
            "youtubeVideoCodec": "h264",
            "youtubeVideoContainer": "mp4",
        },
        response_format="binary",
    ),
    CobaltShortcut(
        slug="instagram-story",
        label="Instagram → MP4",
        description="Download public Instagram reels or stories as MP4 files.",
        payload={
            "service": "instagram",
            "downloadMode": "auto",
            "alwaysProxy": True,
        },
        response_format="binary",
    ),
    CobaltShortcut(
        slug="metadata-only",
        label="Metadata only",
        description="Return the raw JSON response without downloading media.",
        payload={
            "disableMetadata": False,
        },
        response_format="json",
    ),
]


SHORTCUT_REGISTRY = {shortcut.slug: shortcut for shortcut in _SHORTCUTS}


def list_shortcuts() -> Iterable[CobaltShortcut]:
    """Return the registered shortcuts in declaration order."""

    return list(_SHORTCUTS)
