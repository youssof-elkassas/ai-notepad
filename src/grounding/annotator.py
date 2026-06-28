"""
Annotate screenshots with bounding boxes, crosshairs, and labels.
Used to produce the 3 deliverable screenshots and for debug logging.
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from PIL import Image, ImageDraw, ImageFont

from src.automation.screen import Region
from src.utils.logger import get_logger

logger = get_logger(__name__)

# Colors
_BOX_COLOR = (0, 220, 80)       # green bounding box
_CROSS_COLOR = (255, 50, 50)    # red crosshair
_LABEL_BG = (0, 0, 0, 180)     # semi-transparent black label background
_LABEL_FG = (255, 255, 255)     # white label text
_BOX_WIDTH = 3
_CROSS_SIZE = 18
_CROSS_WIDTH = 3


def _try_load_font(size: int = 18) -> ImageFont.ImageFont:
    """Load a readable font, falling back to PIL default if not available."""
    try:
        return ImageFont.truetype("arial.ttf", size)
    except OSError:
        try:
            return ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", size)
        except OSError:
            return ImageFont.load_default()


def annotate(
    img: Image.Image,
    region: Region,
    center: tuple[int, int],
    label: str,
    stage: Optional[str] = None,
) -> Image.Image:
    """
    Draw a bounding box + crosshair + text label on a copy of the image.

    Args:
        img:    Source PIL image (not mutated).
        region: Detected bounding box in screen coordinates.
        center: (x, y) center point to click, in screen coordinates.
        label:  Description text shown on the annotation.
        stage:  Optional stage tag ("Stage 1", "Stage 2", etc.).
    """
    out = img.copy().convert("RGBA")
    overlay = Image.new("RGBA", out.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)

    # Bounding box
    draw.rectangle(
        [(region.x1, region.y1), (region.x2, region.y2)],
        outline=_BOX_COLOR,
        width=_BOX_WIDTH,
    )

    # Crosshair at center
    cx, cy = center
    draw.line([(cx - _CROSS_SIZE, cy), (cx + _CROSS_SIZE, cy)], fill=_CROSS_COLOR, width=_CROSS_WIDTH)
    draw.line([(cx, cy - _CROSS_SIZE), (cx, cy + _CROSS_SIZE)], fill=_CROSS_COLOR, width=_CROSS_WIDTH)

    # Label background + text
    font = _try_load_font(16)
    tag = f"[{stage}] " if stage else ""
    text = f"{tag}{label}  ({cx}, {cy})"

    bbox = draw.textbbox((region.x1, region.y1 - 26), text, font=font)
    draw.rectangle(
        [(bbox[0] - 4, bbox[1] - 2), (bbox[2] + 4, bbox[3] + 2)],
        fill=_LABEL_BG,
    )
    draw.text((region.x1, region.y1 - 26), text, fill=_LABEL_FG, font=font)

    out = Image.alpha_composite(out, overlay).convert("RGB")
    logger.debug("Annotated screenshot: label=%r center=%s", label, center)
    return out


def save_annotated(
    img: Image.Image,
    region: Region,
    center: tuple[int, int],
    label: str,
    path: Path,
    stage: Optional[str] = None,
) -> Path:
    """Annotate and save to disk. Returns the saved path."""
    annotated = annotate(img, region, center, label, stage=stage)
    path.parent.mkdir(parents=True, exist_ok=True)
    annotated.save(path)
    logger.info("Annotated screenshot saved → %s", path)
    return path
