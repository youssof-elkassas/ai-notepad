"""
Desktop screenshot capture and region cropping.
Uses mss for fast, low-latency screen capture.
"""

from __future__ import annotations

import io
import base64
from pathlib import Path
from typing import NamedTuple

import mss
import mss.tools
from PIL import Image

from src.utils.logger import get_logger

logger = get_logger(__name__)


class Region(NamedTuple):
    x1: int
    y1: int
    x2: int
    y2: int

    @property
    def width(self) -> int:
        return self.x2 - self.x1

    @property
    def height(self) -> int:
        return self.y2 - self.y1

    def padded(self, pct: float = 0.20, screen_w: int = 1920, screen_h: int = 1080) -> "Region":
        """Expand region by pct on all sides, clamped to screen bounds."""
        pad_x = int(self.width * pct)
        pad_y = int(self.height * pct)
        return Region(
            x1=max(0, self.x1 - pad_x),
            y1=max(0, self.y1 - pad_y),
            x2=min(screen_w, self.x2 + pad_x),
            y2=min(screen_h, self.y2 + pad_y),
        )

    def map_local_to_screen(self, local_x: int, local_y: int) -> tuple[int, int]:
        """Convert crop-local coordinates back to full-screen coordinates."""
        return self.x1 + local_x, self.y1 + local_y


def capture_desktop() -> Image.Image:
    """
    Capture the entire primary monitor as a PIL Image.
    Uses mss which is significantly faster than pyautogui.screenshot().
    """
    with mss.mss() as sct:
        monitor = sct.monitors[1]  # index 1 = primary monitor
        raw = sct.grab(monitor)
        img = Image.frombytes("RGB", raw.size, raw.bgra, "raw", "BGRX")
        logger.debug("Desktop captured: %dx%d", img.width, img.height)
        return img


def crop_region(img: Image.Image, region: Region) -> Image.Image:
    """Crop an image to the given Region."""
    cropped = img.crop((region.x1, region.y1, region.x2, region.y2))
    logger.debug("Cropped region %s → %dx%d", region, cropped.width, cropped.height)
    return cropped


def image_to_base64(img: Image.Image, fmt: str = "PNG") -> str:
    """Encode a PIL Image as a base64 string for VLM API calls."""
    buf = io.BytesIO()
    img.save(buf, format=fmt)
    return base64.b64encode(buf.getvalue()).decode("utf-8")


def save_screenshot(img: Image.Image, path: Path) -> None:
    """Save a PIL Image to disk."""
    path.parent.mkdir(parents=True, exist_ok=True)
    img.save(path)
    logger.debug("Screenshot saved → %s", path)
