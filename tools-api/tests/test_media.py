import base64
import io
import json
import zipfile
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

import app.routers.media as media_router
from app.main import app
from app.services.download_store import DownloadStore
import app.services.yt_dlp_service as yt_dlp_module
from app.services.yt_dlp_service import DownloadResult, YtDlpService


@pytest.fixture
def client():
    return TestClient(app)


@pytest.fixture
def temp_download_store(monkeypatch, tmp_path):
    store = DownloadStore(root=tmp_path)
    monkeypatch.setattr(media_router, "download_store", store)
    return store


def test_yt_dlp_metadata_endpoint(client, monkeypatch):
    sample_metadata = {
        "id": "demo",
        "title": "Sample",
        "duration": 10,
        "subtitles": {"en": [{"ext": "vtt", "url": "https://example.com/subs.vtt"}]},
        "automatic_captions": {"es": [{"ext": "vtt", "url": "https://example.com/auto.vtt"}]},
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
    assert payload["available_subtitles"]["original"] == ["en"]
    assert payload["available_subtitles"]["auto"] == ["es"]


def test_yt_dlp_download_endpoint(client, monkeypatch, temp_download_store):
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
            "response_format": "download",
            "mode": "video",
            "filename": "custom.mp4",
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["metadata"]["title"] == "Sample"
    download = payload["download"]
    assert download["filename"] == "custom.mp4"
    file_id = download["id"]
    stored_file = temp_download_store.root / file_id / "custom.mp4"
    assert stored_file.exists()
    assert stored_file.read_bytes() == b"video-bytes"

    file_response = client.get(f"/media/yt-dlp/files/{file_id}")
    assert file_response.status_code == 200
    assert file_response.content == b"video-bytes"
    assert file_response.headers["content-type"] == "video/mp4"
    metadata_header = file_response.headers.get("X-YtDlp-Metadata")
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


def test_yt_dlp_sanitises_filename_override(client, monkeypatch, temp_download_store):
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
            "response_format": "download",
            "mode": "video",
            "filename": "../custom/video.mp4",
        },
    )

    assert response.status_code == 200
    assert captured["filename"] == "video.mp4"


def test_yt_dlp_subtitle_download(client, monkeypatch, temp_download_store):
    metadata = {"id": "demo", "title": "Sample"}

    def fake_download_subtitles(url: str, *, options, filename_override=None):
        assert options["subtitleslangs"] == ["en"]
        assert options["writeautomaticsub"] is True
        return DownloadResult(
            content=b"subtitle-bytes",
            filename=filename_override or "sample.vtt",
            content_type="text/vtt",
            metadata=metadata,
        )

    monkeypatch.setattr(media_router.yt_dlp_service, "download_subtitles", fake_download_subtitles)

    response = client.post(
        "/media/yt-dlp",
        json={
            "url": "https://example.com/video",
            "response_format": "download",
            "mode": "subtitles",
            "subtitle_languages": ["en"],
            "subtitle_source": "auto",
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["metadata"]["mode"] == "subtitles"
    download = payload["download"]
    assert download["filename"].endswith(".vtt")
    file_id = download["id"]
    stored_file = next((temp_download_store.root / file_id).glob("*.vtt"))
    assert stored_file.read_bytes() == b"subtitle-bytes"


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


def test_download_subtitles_packages_multiple_languages(monkeypatch):
    captured_options: dict[str, object] = {}

    class FakeYoutubeDL:
        def __init__(self, options):
            self.options = options

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def extract_info(self, url, download):
            assert url == "https://example.com/video"
            assert download is True
            captured_options.update(self.options)
            outtmpl = self.options.get("outtmpl")
            assert outtmpl is not None
            out_path = Path(outtmpl)
            directory = out_path.parent
            directory.mkdir(parents=True, exist_ok=True)
            (directory / "video.en.vtt").write_text("English", encoding="utf-8")
            (directory / "video.fr.srt").write_text("Français", encoding="utf-8")
            return {"id": "demo", "title": "Sample"}

    class FakeYtDlpModule:
        YoutubeDL = FakeYoutubeDL

    monkeypatch.setattr(yt_dlp_module, "_ensure_yt_dlp", lambda: FakeYtDlpModule())

    service = YtDlpService()
    result = service.download_subtitles(
        "https://example.com/video",
        options={"writesubtitles": True, "subtitleslangs": ["en", "fr"]},
    )

    assert captured_options["writesubtitles"] is True
    assert captured_options["skip_download"] is True
    assert captured_options["subtitleslangs"] == ["en", "fr"]
    assert result.content_type == "application/zip"
    assert result.filename == "subtitles.zip"
    assert sorted(result.metadata["subtitle_files"]) == ["video.en.vtt", "video.fr.srt"]

    with zipfile.ZipFile(io.BytesIO(result.content)) as archive:
        assert sorted(archive.namelist()) == ["video.en.vtt", "video.fr.srt"]
        assert archive.read("video.en.vtt") == b"English"
        assert archive.read("video.fr.srt") == "Français".encode("utf-8")


