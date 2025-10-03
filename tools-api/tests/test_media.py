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
    sample_metadata = {"id": "demo", "title": "Sample", "duration": 10}

    def fake_extract(url: str, *, options):
        assert url == "https://example.com/video"
        assert options["noplaylist"] is True
        return sample_metadata

    monkeypatch.setattr(media_router.yt_dlp_service, "extract_info", fake_extract)

    response = client.post(
        "/media/yt-dlp",
        json={"url": "https://example.com/video"},
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

