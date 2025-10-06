import io
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

import app.routers.ffmpeg as ffmpeg_router
from app.main import app
from app.services.ffmpeg_service import ConversionResult, FfmpegServiceError


@pytest.fixture
def client():
    return TestClient(app)


def test_list_formats_returns_data(monkeypatch, client):
    def fake_list_formats():
        return {"inputs": ["wav"], "outputs": ["mp3"], "common": ["wav"]}

    monkeypatch.setattr(ffmpeg_router.ffmpeg_service, "list_formats", fake_list_formats)

    response = client.get("/media/ffmpeg/formats")
    assert response.status_code == 200
    payload = response.json()
    assert payload["inputs"] == ["wav"]
    assert payload["outputs"] == ["mp3"]
    assert payload["common"] == ["wav"]


def test_list_formats_failure(monkeypatch, client):
    def fake_list_formats():
        raise FfmpegServiceError("ffmpeg unavailable")

    monkeypatch.setattr(ffmpeg_router.ffmpeg_service, "list_formats", fake_list_formats)

    response = client.get("/media/ffmpeg/formats")
    assert response.status_code == 503
    assert response.json()["detail"] == "ffmpeg unavailable"


def test_convert_media_returns_file(monkeypatch, client, tmp_path):
    output_path = tmp_path / "converted.mp3"
    output_path.write_bytes(b"audio")
    result = ConversionResult(
        output_path=output_path,
        filename="converted.mp3",
        media_type="audio/mpeg",
        workdir=tmp_path,
    )

    monkeypatch.setattr(ffmpeg_router.ffmpeg_service, "convert_upload", lambda *args, **kwargs: result)

    cleaned = {}

    def fake_cleanup(directory: Path | str | None):
        cleaned["path"] = directory

    monkeypatch.setattr(ffmpeg_router.ffmpeg_service, "cleanup_directory", fake_cleanup)

    files = {"file": ("demo.wav", io.BytesIO(b"data"), "audio/wav")}
    response = client.post(
        "/media/ffmpeg/convert",
        data={"source_format": "wav", "target_format": "mp3"},
        files=files,
    )

    assert response.status_code == 200
    assert response.headers["content-type"] == "audio/mpeg"
    assert response.content == b"audio"
    assert cleaned["path"] == tmp_path


def test_convert_media_failure(monkeypatch, client):
    def fake_convert_upload(*args, **kwargs):
        raise FfmpegServiceError("conversion failed")

    monkeypatch.setattr(ffmpeg_router.ffmpeg_service, "convert_upload", fake_convert_upload)

    files = {"file": ("demo.wav", io.BytesIO(b"data"), "audio/wav")}
    response = client.post(
        "/media/ffmpeg/convert",
        data={"target_format": "mp3"},
        files=files,
    )

    assert response.status_code == 400
    assert response.json()["detail"] == "conversion failed"
