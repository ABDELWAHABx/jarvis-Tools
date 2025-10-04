"""Before/after animation generator inspired by FUT-Coding/beforeandafter."""
from __future__ import annotations

import math
import tempfile
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, Tuple

import imageio
import numpy as np
from PIL import Image, ImageDraw, ImageFont, ImageOps


class BeforeAfterError(RuntimeError):
    """Raised when a before/after animation cannot be produced."""


@dataclass
class BeforeAfterResult:
    """Binary animation payload returned by :class:`BeforeAfterService`."""

    content: bytes
    content_type: str
    filename: str
    metadata: Dict[str, int | float | str | bool]


class BeforeAfterService:
    """Create looping swipe animations from two images.

    The implementation ports the core behaviour of
    https://github.com/FUTC-Coding/beforeandafter to Python so the effect can be
    consumed via the Tools API. The animation mimics the JavaScript version by
    animating a divider line across the frame twice using a cosine easing
    function so the clip loops seamlessly.
    """

    def __init__(
        self,
        *,
        duration_seconds: float = 6.0,
        fps: int = 30,
        cycles: int = 2,
        line_thickness: int = 6,
        add_text: bool = False,
        overlay_text: str | None = None,
        text_baseline_offset: int = 120,
        text_fill: Tuple[int, int, int] = (40, 40, 40),
    ) -> None:
        if duration_seconds <= 0:
            raise BeforeAfterError("Duration must be greater than zero")
        if fps <= 0:
            raise BeforeAfterError("FPS must be greater than zero")
        if cycles <= 0:
            raise BeforeAfterError("Cycles must be a positive integer")

        self.duration_seconds = float(duration_seconds)
        self.fps = int(fps)
        self.cycles = int(cycles)
        self.line_thickness = max(1, int(line_thickness))
        self.add_text = bool(add_text)
        self.overlay_text = overlay_text or ""
        self.text_baseline_offset = max(0, int(text_baseline_offset))
        self.text_fill = tuple(text_fill)

    def generate(
        self,
        before_image: Image.Image,
        after_image: Image.Image,
        *,
        frame_size: Tuple[int, int] | None = None,
    ) -> BeforeAfterResult:
        if before_image.mode not in ("RGB", "RGBA"):
            before_image = before_image.convert("RGB")
        if after_image.mode not in ("RGB", "RGBA"):
            after_image = after_image.convert("RGB")

        width, height = self._resolve_frame_size(before_image.size, after_image.size, frame_size)
        before = ImageOps.fit(before_image, (width, height), Image.Resampling.LANCZOS)
        after = ImageOps.fit(after_image, (width, height), Image.Resampling.LANCZOS)

        frames = list(self._build_frames(before, after))

        metadata = {
            "width": width,
            "height": height,
            "fps": self.fps,
            "duration_seconds": self.duration_seconds,
            "cycles": self.cycles,
            "line_thickness": self.line_thickness,
            "add_text": self.add_text,
        }

        # imageio uses numpy arrays, so convert the PIL frames.
        np_frames = [np.asarray(frame) for frame in frames]

        temp_file = tempfile.NamedTemporaryFile(suffix=".mp4", delete=False)
        temp_file.close()

        try:
            with imageio.get_writer(
                temp_file.name,
                fps=self.fps,
                codec="libx264",
                quality=8,
                macro_block_size=None,
            ) as writer:
                for array in np_frames:
                    writer.append_data(array)
            content = Path(temp_file.name).read_bytes()
        except (RuntimeError, ValueError, OSError) as exc:  # pragma: no cover - depends on ffmpeg availability
            raise BeforeAfterError("Failed to encode animation with ffmpeg") from exc
        finally:
            try:
                Path(temp_file.name).unlink(missing_ok=True)
            except OSError:
                pass

        filename = f"before-after-{uuid.uuid4().hex[:8]}.mp4"
        return BeforeAfterResult(
            content=content,
            content_type="video/mp4",
            filename=filename,
            metadata=metadata,
        )

    def _build_frames(self, before: Image.Image, after: Image.Image) -> Iterable[Image.Image]:
        total_frames = max(2, int(self.fps * self.duration_seconds))
        width, height = before.size

        for index in range(total_frames):
            normalized_time = index / (total_frames - 1)
            progress = (1 - math.cos(normalized_time * math.pi * self.cycles)) / 2
            divider_x = int(progress * width)

            frame = before.copy()
            mask = Image.new("L", before.size, 0)
            mask_draw = ImageDraw.Draw(mask)
            mask_draw.rectangle([divider_x, 0, width, height], fill=255)
            frame.paste(after, mask=mask)

            draw = ImageDraw.Draw(frame)
            self._draw_divider(draw, divider_x, height)

            if self.add_text and self.overlay_text:
                self._draw_overlay_text(draw, width, height)

            yield frame

    def _draw_divider(self, draw: ImageDraw.ImageDraw, x_position: int, height: int) -> None:
        outline_color = (20, 20, 20)
        main_color = (255, 255, 255)

        draw.line(
            [(x_position, -10), (x_position, height + 10)],
            fill=outline_color,
            width=self.line_thickness + 4,
        )
        draw.line(
            [(x_position, -10), (x_position, height + 10)],
            fill=main_color,
            width=self.line_thickness,
        )

    def _draw_overlay_text(self, draw: ImageDraw.ImageDraw, width: int, height: int) -> None:
        try:
            font = ImageFont.truetype("arial.ttf", size=max(24, width // 18))
        except OSError:
            font = ImageFont.load_default()

        text = self.overlay_text
        text_bbox = draw.textbbox((0, 0), text, font=font)
        text_width = text_bbox[2] - text_bbox[0]
        x_position = (width - text_width) // 2
        y_position = max(0, height - self.text_baseline_offset)

        draw.text(
            (x_position, y_position),
            text,
            font=font,
            fill=self.text_fill,
        )

    @staticmethod
    def _resolve_frame_size(
        before_size: Tuple[int, int],
        after_size: Tuple[int, int],
        requested: Tuple[int, int] | None,
    ) -> Tuple[int, int]:
        if requested:
            width, height = requested
            if width <= 0 or height <= 0:
                raise BeforeAfterError("Requested frame size must be positive")
            return int(width), int(height)

        # Default to the smaller shared dimensions so we never upscale drastically.
        width = min(before_size[0], after_size[0])
        height = min(before_size[1], after_size[1])
        if width <= 0 or height <= 0:
            raise BeforeAfterError("Input images must have positive dimensions")
        return width, height

