"""Port of FUTC-Coding/halations image glow effect."""
from __future__ import annotations

import io
from dataclasses import dataclass
from typing import Dict

import numpy as np
from PIL import Image, ImageFilter


class HalationsError(RuntimeError):
    """Raised when an image cannot be processed with the halations effect."""


@dataclass
class HalationsResult:
    """Binary payload for the generated halations image."""

    content: bytes
    filename: str
    content_type: str
    metadata: Dict[str, int | float]


class HalationsService:
    """Apply a highlight glow reminiscent of the halations web tool."""

    def __init__(
        self,
        *,
        blur_amount: float = 10.0,
        brightness_threshold: int = 200,
        strength: float = 50.0,
    ) -> None:
        if blur_amount < 0:
            raise HalationsError("Blur amount must be non-negative")
        if brightness_threshold < 0 or brightness_threshold > 255:
            raise HalationsError("Brightness threshold must be between 0 and 255")

        self.blur_amount = float(blur_amount)
        self.brightness_threshold = int(brightness_threshold)
        self.strength = float(strength)

    def apply(self, image: Image.Image) -> HalationsResult:
        if image.mode != "RGB":
            image = image.convert("RGB")

        original = np.asarray(image, dtype=np.float32)
        brightness = original.mean(axis=2)

        mask = (brightness >= self.brightness_threshold).astype(np.float32)
        mask_image = Image.fromarray((mask * 255).astype(np.uint8))

        if self.blur_amount > 0:
            mask_image = mask_image.filter(ImageFilter.GaussianBlur(radius=self.blur_amount))

        blurred_mask = np.asarray(mask_image, dtype=np.float32) / 255.0

        overlay = np.zeros_like(original)
        overlay[..., 0] = np.clip(blurred_mask * 255 + self.strength, 0, 255)

        result = self._screen_blend(original, overlay)

        buffer = io.BytesIO()
        Image.fromarray(result.astype(np.uint8)).save(buffer, format="JPEG", quality=95)

        metadata = {
            "width": int(image.width),
            "height": int(image.height),
            "blur_amount": self.blur_amount,
            "brightness_threshold": self.brightness_threshold,
            "strength": self.strength,
        }

        filename = "halations-result.jpg"
        return HalationsResult(
            content=buffer.getvalue(),
            filename=filename,
            content_type="image/jpeg",
            metadata=metadata,
        )

    @staticmethod
    def _screen_blend(base: np.ndarray, overlay: np.ndarray) -> np.ndarray:
        base_norm = base / 255.0
        overlay_norm = overlay / 255.0
        blended = 1 - (1 - base_norm) * (1 - overlay_norm)
        return np.clip(blended * 255.0, 0, 255)

