import base64
import io
import json
import zipfile
from typing import Any, Dict

import pytest
from fastapi.testclient import TestClient

import app.routers.js_tools as js_tools_router
from app.config import settings
from app.main import app
from app.services import js_tool_service
from app.services.cobalt_gateway import CobaltProcessResult
from app.services.cobalt_service import CobaltBinaryResult, CobaltError
from app.services.js_tool_service import PanosplitterResult


@pytest.fixture
def client():
    return TestClient(app)


def _build_manifest() -> Dict[str, Any]:
    return {
        "metadata": {
            "mode": "standard",
            "slice_count": 2,
            "slice_width": 1080,
            "slice_height": 1350,
            "scaled_width": 2160,
            "scaled_height": 1350,
            "original_filename": "demo.jpg",
        },
        "slices": [
            {
                "filename": "slice-01.jpg",
                "width": 1080,
                "height": 1350,
                "content_type": "image/jpeg",
            },
            {
                "filename": "slice-02.jpg",
                "width": 1080,
                "height": 1350,
                "content_type": "image/jpeg",
            },
        ],
        "full_view": {
            "filename": "full-view.jpg",
            "width": 1080,
            "height": 1350,
            "content_type": "image/jpeg",
        },
    }


def _encode_zip_with_manifest(manifest: Dict[str, Any]) -> str:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("slice-01.jpg", b"slice-one")
        archive.writestr("slice-02.jpg", b"slice-two")
        archive.writestr("full-view.jpg", b"full-view")
        archive.writestr("manifest.json", json.dumps(manifest))
    return base64.b64encode(buffer.getvalue()).decode("utf-8")


def test_run_panosplitter_service(monkeypatch):
    monkeypatch.setattr(js_tool_service, "_ensure_node_available", lambda: None)
    monkeypatch.setattr(js_tool_service, "_ensure_dependencies", lambda _tool_dir: None)

    def fake_invoke(cli_path, input_path, output_dir, mode, timeout=None):
        # Create fake output assets
        (output_dir / "slice-01.jpg").write_bytes(b"slice-one")
        (output_dir / "slice-02.jpg").write_bytes(b"slice-two")
        (output_dir / "full-view.jpg").write_bytes(b"full-view")
        return PanosplitterResult(
            mode=mode,
            slice_count=2,
            slice_width=1080,
            slice_height=1350,
            scaled_width=2160,
            scaled_height=1350,
            slices=[
                {"filename": "slice-01.jpg", "width": 1080, "height": 1350},
                {"filename": "slice-02.jpg", "width": 1080, "height": 1350},
            ],
            full_view={"filename": "full-view.jpg", "width": 1080, "height": 1350},
        )

    monkeypatch.setattr(js_tool_service, "_invoke_panosplitter_cli", fake_invoke)

    result = js_tool_service.run_panosplitter(b"image-bytes", filename="panorama.jpg")

    assert result["metadata"]["slice_count"] == 2
    assert len(result["slices"]) == 2
    assert base64.b64decode(result["slices"][0]["base64"]) == b"slice-one"
    assert result["full_view"]["width"] == 1080
    assert result["manifest"]["metadata"]["slice_count"] == 2

    zip_payload = base64.b64decode(result["zip_file"]["base64"])
    with zipfile.ZipFile(io.BytesIO(zip_payload)) as archive:
        assert set(archive.namelist()) == {"full-view.jpg", "slice-01.jpg", "slice-02.jpg", "manifest.json"}
        manifest = json.loads(archive.read("manifest.json"))
        assert manifest["metadata"]["slice_count"] == 2


def test_panosplitter_endpoint(client, monkeypatch):
    manifest = _build_manifest()
    sample_result = {
        "metadata": manifest["metadata"],
        "zip_file": {
            "filename": "panosplitter_slices.zip",
            "base64": _encode_zip_with_manifest(manifest),
            "content_type": "application/zip",
        },
        "slices": [
            {
                "filename": "slice-01.jpg",
                "content_type": "image/jpeg",
                "base64": base64.b64encode(b"slice-one").decode("utf-8"),
                "width": 1080,
                "height": 1350,
            }
        ],
        "full_view": {
            "filename": "full-view.jpg",
            "content_type": "image/jpeg",
            "base64": base64.b64encode(b"full-view").decode("utf-8"),
            "width": 1080,
            "height": 1350,
        },
        "manifest": manifest,
    }

    fake_runner = lambda *args, **kwargs: sample_result

    monkeypatch.setattr(js_tool_service, "run_panosplitter", fake_runner)
    monkeypatch.setattr(js_tools_router, "run_panosplitter", fake_runner)

    response = client.post(
        "/js-tools/panosplitter",
        files={"image": ("demo.jpg", b"image-bytes", "image/jpeg")},
        data={"high_res": "false"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["metadata"]["slice_count"] == 2
    assert payload["manifest"]["full_view"]["filename"] == "full-view.jpg"


def test_panosplitter_binary_response(client, monkeypatch):
    manifest = _build_manifest()
    sample_result = {
        "metadata": manifest["metadata"],
        "zip_file": {
            "filename": "panosplitter_slices.zip",
            "base64": _encode_zip_with_manifest(manifest),
            "content_type": "application/zip",
        },
        "slices": [
            {
                "filename": "slice-01.jpg",
                "content_type": "image/jpeg",
                "base64": base64.b64encode(b"slice-one").decode("utf-8"),
                "width": 1080,
                "height": 1350,
            }
        ],
        "full_view": {
            "filename": "full-view.jpg",
            "content_type": "image/jpeg",
            "base64": base64.b64encode(b"full-view").decode("utf-8"),
            "width": 1080,
            "height": 1350,
        },
        "manifest": manifest,
    }

    fake_runner = lambda *args, **kwargs: sample_result

    monkeypatch.setattr(js_tool_service, "run_panosplitter", fake_runner)
    monkeypatch.setattr(js_tools_router, "run_panosplitter", fake_runner)

    response = client.post(
        "/js-tools/panosplitter",
        files={"image": ("demo.jpg", b"image-bytes", "image/jpeg")},
        data={"high_res": "false"},
        params={"response_format": "binary"},
    )

    assert response.status_code == 200
    assert response.headers["content-type"] == "application/zip"
    encoded_manifest = response.headers.get("X-Panosplitter-Manifest")
    assert encoded_manifest is not None
    decoded_manifest = json.loads(base64.b64decode(encoded_manifest).decode("utf-8"))
    assert decoded_manifest["metadata"]["slice_count"] == 2

    with zipfile.ZipFile(io.BytesIO(response.content)) as archive:
        assert set(archive.namelist()) == {"slice-01.jpg", "slice-02.jpg", "full-view.jpg", "manifest.json"}


def test_cobalt_endpoint_requires_configuration(client, monkeypatch):
    monkeypatch.setattr(settings, "COBALT_API_BASE_URL", "")
    monkeypatch.setattr(settings, "COBALT_API_BASE_URL_FALLBACK", False)
    monkeypatch.setattr(js_tools_router, "_cobalt_gateway", None)

    def raise_gateway(**_kwargs):
        raise CobaltError("no cobalt backends available")

    monkeypatch.setattr(js_tools_router, "create_gateway", raise_gateway)

    response = client.post("/js-tools/cobalt", json={"url": "https://example.com/video"})
    assert response.status_code == 503


def test_cobalt_endpoint_json_response(client, monkeypatch):
    monkeypatch.setattr(settings, "COBALT_API_BASE_URL", "https://cobalt.example")

    captured: Dict[str, Any] = {}

    class DummyGateway:
        has_remote = True
        has_local = False

        async def process(self, payload: Dict[str, Any], *, expect_binary: bool, filename_override=None):
            captured["payload"] = payload
            captured["expect_binary"] = expect_binary
            return CobaltProcessResult(
                payload={"status": "tunnel", "url": "https://download", "filename": "demo.mp4"},
                binary=None,
                used_local_fallback=False,
                source_label="remote.test",
            )

    monkeypatch.setattr(js_tools_router, "_cobalt_gateway", DummyGateway())

    response = client.post(
        "/js-tools/cobalt",
        json={"url": "https://example.com/video", "audioFormat": "mp3"},
    )

    assert response.status_code == 200
    assert response.headers["X-Cobalt-Backend"] == "remote"
    assert response.headers["X-Cobalt-Source"] == "remote.test"
    payload = response.json()
    assert payload["status"] == "tunnel"
    assert captured["payload"]["audioFormat"] == "mp3"
    assert captured["expect_binary"] is False


def test_cobalt_endpoint_binary_response(client, monkeypatch):
    monkeypatch.setattr(settings, "COBALT_API_BASE_URL", "https://cobalt.example")

    class DummyGateway:
        has_remote = True
        has_local = False

        async def process(self, payload: Dict[str, Any], *, expect_binary: bool, filename_override=None):
            assert expect_binary is True
            assert filename_override == "custom.mp4"
            metadata = {"status": "tunnel", "url": "https://download", "filename": "remote.mp4"}
            encoded = base64.b64encode(json.dumps(metadata).encode("utf-8")).decode("utf-8")
            binary = CobaltBinaryResult(
                content=b"binary-data",
                filename="cobalt.mp4" if filename_override is None else filename_override,
                content_type="video/mp4",
                metadata=metadata,
                encoded_metadata=encoded,
            )
            return CobaltProcessResult(
                payload=metadata,
                binary=binary,
                used_local_fallback=False,
                source_label="remote.test",
            )

    monkeypatch.setattr(js_tools_router, "_cobalt_gateway", DummyGateway())

    response = client.post(
        "/js-tools/cobalt",
        json={
            "url": "https://example.com/video",
            "response_format": "binary",
            "download_filename": "custom.mp4",
        },
    )

    assert response.status_code == 200
    assert response.headers["content-type"] == "video/mp4"
    assert response.headers["Content-Disposition"].endswith("custom.mp4")
    assert response.headers["X-Cobalt-Backend"] == "remote"
    assert response.headers["X-Cobalt-Source"] == "remote.test"
    metadata_header = response.headers["X-Cobalt-Metadata"]
    assert json.loads(base64.b64decode(metadata_header)) == {
        "status": "tunnel",
        "url": "https://download",
        "filename": "remote.mp4",
    }
    assert response.content == b"binary-data"


def test_cobalt_shortcut_json_response(client, monkeypatch):
    monkeypatch.setattr(settings, "COBALT_API_BASE_URL", "https://cobalt.example")

    captured: Dict[str, Any] = {}

    class DummyGateway:
        has_remote = True
        has_local = False

        async def process(self, payload: Dict[str, Any], *, expect_binary: bool, filename_override=None):
            captured["payload"] = payload
            captured["expect_binary"] = expect_binary
            return CobaltProcessResult(
                payload={"status": "redirect", "url": "https://download/audio.mp3", "filename": "audio.mp3"},
                binary=None,
                used_local_fallback=False,
                source_label="remote.test",
            )

    monkeypatch.setattr(js_tools_router, "_cobalt_gateway", DummyGateway())

    response = client.post(
        "/js-tools/cobalt/shortcuts/YOUTUBE-AUDIO",
        json={"url": "https://example.com/watch", "response_format": "json"},
    )

    assert response.status_code == 200
    assert response.headers["X-Cobalt-Backend"] == "remote"
    payload = response.json()
    assert payload["shortcut"] == "youtube-audio"
    assert payload["download_url"] == "https://download/audio.mp3"
    assert captured["payload"]["audioFormat"] == "mp3"
    assert captured["payload"]["downloadMode"] == "audio"
    assert captured["payload"]["url"] == "https://example.com/watch"
    assert captured["expect_binary"] is False


def test_cobalt_shortcut_binary_response(client, monkeypatch):
    monkeypatch.setattr(settings, "COBALT_API_BASE_URL", "https://cobalt.example")

    class DummyGateway:
        has_remote = True
        has_local = False

        async def process(self, payload: Dict[str, Any], *, expect_binary: bool, filename_override=None):
            assert expect_binary is True
            assert payload["service"] == "instagram"
            assert payload["alwaysProxy"] is True
            metadata = {"status": "tunnel", "url": "https://download/video.mp4", "filename": "video.mp4"}
            encoded = base64.b64encode(json.dumps(metadata).encode("utf-8")).decode("utf-8")
            binary = CobaltBinaryResult(
                content=b"shortcut-media",
                filename=filename_override or "video.mp4",
                content_type="video/mp4",
                metadata=metadata,
                encoded_metadata=encoded,
            )
            return CobaltProcessResult(
                payload=metadata,
                binary=binary,
                used_local_fallback=False,
                source_label="remote.test",
            )

    monkeypatch.setattr(js_tools_router, "_cobalt_gateway", DummyGateway())

    response = client.post(
        "/js-tools/cobalt/shortcuts/instagram-story",
        json={
            "url": "https://instagram.com/reel/abc",
            "download_filename": "shortcut.mp4",
        },
    )

    assert response.status_code == 200
    assert response.headers["content-type"] == "video/mp4"
    assert response.headers["Content-Disposition"].endswith("shortcut.mp4")
    assert response.headers["X-Cobalt-Metadata"]
    assert response.headers["X-Cobalt-Backend"] == "remote"
    assert response.content == b"shortcut-media"
