from __future__ import annotations

import base64
import io

from fastapi.testclient import TestClient
from PIL import Image

from app.main import app


def _create_image_bytes(color: tuple[int, int, int], size: tuple[int, int] = (64, 64)) -> bytes:
    image = Image.new("RGB", size, color=color)
    buffer = io.BytesIO()
    image.save(buffer, format="JPEG")
    return buffer.getvalue()


def test_before_after_default_message():
    client = TestClient(app)

    before_bytes = _create_image_bytes((255, 0, 0))
    after_bytes = _create_image_bytes((0, 0, 255))

    response = client.post(
        "/image-tools/before-after",
        files={
            "before_image": ("before.jpg", before_bytes, "image/jpeg"),
            "after_image": ("after.jpg", after_bytes, "image/jpeg"),
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["content_type"] == "video/mp4"
    assert payload["message"] is not None

    video_bytes = base64.b64decode(payload["video_base64"])
    # Minimal assurance that we produced an MP4 container.
    assert video_bytes[4:8] == b"ftyp"


def test_before_after_binary_headers():
    client = TestClient(app)

    before_bytes = _create_image_bytes((255, 255, 255))
    after_bytes = _create_image_bytes((0, 0, 0))

    response = client.post(
        "/image-tools/before-after",
        files={
            "before_image": ("before.jpg", before_bytes, "image/jpeg"),
            "after_image": ("after.jpg", after_bytes, "image/jpeg"),
        },
        data={
            "duration_seconds": "2",
            "fps": "15",
            "line_thickness": "4",
        },
        params={"response_format": "binary"},
    )

    assert response.status_code == 200
    assert response.headers["content-type"] == "video/mp4"
    assert "X-Before-After-Metadata" in response.headers
    # Custom parameters suppress the hint header.
    assert "X-Before-After-Hint" not in response.headers


def test_halations_default_hint():
    client = TestClient(app)

    image_bytes = _create_image_bytes((200, 200, 200))

    response = client.post(
        "/image-tools/halations",
        files={"image": ("input.jpg", image_bytes, "image/jpeg")},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["content_type"] == "image/jpeg"
    assert payload["message"] is not None

    processed = base64.b64decode(payload["image_base64"])
    assert processed.startswith(b"\xff\xd8\xff")  # JPEG magic number


def test_halations_binary_metadata():
    client = TestClient(app)

    image_bytes = _create_image_bytes((180, 180, 180))

    response = client.post(
        "/image-tools/halations",
        files={"image": ("input.jpg", image_bytes, "image/jpeg")},
        data={
            "blur_amount": "5",
            "brightness_threshold": "150",
            "strength": "80",
        },
        params={"response_format": "binary"},
    )

    assert response.status_code == 200
    assert response.headers["content-type"] == "image/jpeg"
    assert "X-Halations-Metadata" in response.headers
    assert "X-Halations-Hint" not in response.headers
