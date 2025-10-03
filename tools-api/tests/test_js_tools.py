import base64
import io
import zipfile

import pytest
from fastapi.testclient import TestClient

import app.routers.js_tools as js_tools_router
from app.main import app
from app.services import js_tool_service
from app.services.js_tool_service import PanosplitterResult


@pytest.fixture
def client():
    return TestClient(app)


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

    zip_payload = base64.b64decode(result["zip_file"]["base64"])
    with zipfile.ZipFile(io.BytesIO(zip_payload)) as archive:
        assert set(archive.namelist()) == {"full-view.jpg", "slice-01.jpg", "slice-02.jpg"}


def test_panosplitter_endpoint(client, monkeypatch):
    sample_result = {
        "metadata": {
            "mode": "standard",
            "slice_count": 2,
            "slice_width": 1080,
            "slice_height": 1350,
            "scaled_width": 2160,
            "scaled_height": 1350,
            "original_filename": "demo.jpg",
        },
        "zip_file": {
            "filename": "panosplitter_slices.zip",
            "base64": base64.b64encode(b"zip-bytes").decode("utf-8"),
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
    assert payload["slices"][0]["filename"] == "slice-01.jpg"
