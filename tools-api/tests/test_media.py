import base64
import json

import pytest
from fastapi.testclient import TestClient

import app.routers.media as media_router
from app.main import app
from app.services.yt_dlp_service import DownloadResult


@pytest.fixture
def client():
    return TestClient(app)


def test_yt_dlp_metadata_endpoint(client, monkeypatch):
    sample_metadata = {
        "id": "demo",
        "title": "Sample",
        "duration": 10,
        "requested_subtitles": {"en": {"ext": "vtt", "url": "https://example.com/subs.vtt"}},
    }

    def fake_extract(url: str, *, options):
        assert url == "https://example.com/video"
        assert options["noplaylist"] is True
        assert options["format"] == "best"
        assert options["playlist_items"] == "1-3"
        assert options["http_headers"] == {"Cookie": "session=abc"}
        assert options["proxy"] == "socks5://localhost:9050"
        assert options["writesubtitles"] is True
        assert options["writeautomaticsub"] is True
        assert options["subtitleslangs"] == ["en", "es"]
        return sample_metadata

    monkeypatch.setattr(media_router.yt_dlp_service, "extract_info", fake_extract)

    response = client.post(
        "/media/yt-dlp",
        json={
            "url": "https://example.com/video",
            "options": {
                "format": "best",
                "playlist_items": "1-3",
                "http_headers": {"Cookie": "session=abc"},
                "proxy": "socks5://localhost:9050",
                "writesubtitles": True,
                "writeautomaticsub": True,
                "subtitleslangs": ["en", "es"],
            },
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["metadata"] == sample_metadata


def test_yt_dlp_binary_endpoint(client, monkeypatch):
    metadata = {"id": "demo", "title": "Sample", "ext": "mp4"}

    def fake_download(url: str, *, options, filename_override=None):
        assert filename_override == "custom.mp4"
        return DownloadResult(
            content=b"video-bytes",
            filename=filename_override or "sample.mp4",
            content_type="video/mp4",
            metadata=metadata,
        )

    monkeypatch.setattr(media_router.yt_dlp_service, "download", fake_download)

    response = client.post(
        "/media/yt-dlp",
        json={
            "url": "https://example.com/video",
            "response_format": "binary",
            "filename": "custom.mp4",
        },
    )

    assert response.status_code == 200
    assert response.content == b"video-bytes"
    assert response.headers["content-type"] == "video/mp4"
    assert response.headers["Content-Disposition"].endswith("custom.mp4")

    metadata_header = response.headers.get("X-YtDlp-Metadata")
    assert metadata_header is not None
    decoded = json.loads(base64.b64decode(metadata_header))
    assert decoded["title"] == "Sample"


def test_yt_dlp_failure_returns_error(client, monkeypatch):
    def fake_extract(url: str, *, options):
        raise media_router.YtDlpServiceError("boom")

    monkeypatch.setattr(media_router.yt_dlp_service, "extract_info", fake_extract)

    response = client.post(
        "/media/yt-dlp",
        json={"url": "https://example.com/video"},
    )

    assert response.status_code == 502
    assert response.json()["detail"] == "boom"


def test_yt_dlp_accepts_urls_without_scheme(client, monkeypatch):
    captured: dict[str, str] = {}

    def fake_extract(url: str, *, options):
        captured["url"] = url
        return {"id": "demo"}

    monkeypatch.setattr(media_router.yt_dlp_service, "extract_info", fake_extract)

    response = client.post(
        "/media/yt-dlp",
        json={"url": "youtube.com/watch?v=123"},
    )

    assert response.status_code == 200
    assert captured["url"] == "https://youtube.com/watch?v=123"


def test_yt_dlp_sanitises_filename_override(client, monkeypatch):
    captured: dict[str, str | None] = {}

    def fake_download(url: str, *, options, filename_override=None):
        captured["filename"] = filename_override
        return DownloadResult(
            content=b"bytes",
            filename="video.mp4",
            content_type="video/mp4",
            metadata={"id": "demo"},
        )

    monkeypatch.setattr(media_router.yt_dlp_service, "download", fake_download)

    response = client.post(
        "/media/yt-dlp",
        json={
            "url": "https://example.com/video",
            "response_format": "binary",
            "filename": "../custom/video.mp4",
        },
    )

    assert response.status_code == 200
    assert captured["filename"] == "video.mp4"


def test_yt_dlp_subtitle_languages_accepts_string(client, monkeypatch):
    captured_options: dict[str, object] = {}

    def fake_extract(url: str, *, options):
        captured_options.update(options)
        return {"id": "demo"}

    monkeypatch.setattr(media_router.yt_dlp_service, "extract_info", fake_extract)

    response = client.post(
        "/media/yt-dlp",
        json={
            "url": "https://example.com/video",
            "options": {
                "subtitleslangs": "en, es ,",
            },
        },
    )

    assert response.status_code == 200
    assert captured_options["subtitleslangs"] == ["en", "es"]

