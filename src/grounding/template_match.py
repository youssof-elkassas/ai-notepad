"""Last-resort grounding via BotCity OpenCV template matching."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Optional

from PIL import Image
from dotenv import load_dotenv

from botcity.core import cv2find

from src.automation.screen import Region
from src.utils.logger import get_logger

load_dotenv()

logger = get_logger(__name__)

DEFAULT_TEMPLATE_PATH = Path("resources/templates/notepad_shortcut.png")
DEFAULT_TEMPLATE_MATCHING = 0.85
DEFAULT_TEMPLATE_CROP_SIZE = 80

_TEMPLATE_MATCH_FALLBACK = os.getenv("TEMPLATE_MATCH_FALLBACK", "true").lower() in (
    "1", "true", "yes", "on",
)


def is_template_fallback_enabled() -> bool:
    return _TEMPLATE_MATCH_FALLBACK


def get_template_path() -> Path:
    raw = os.getenv("TEMPLATE_IMAGE_PATH")
    if raw:
        return Path(raw)
    return DEFAULT_TEMPLATE_PATH


def get_template_matching() -> float:
    return float(os.getenv("TEMPLATE_MATCHING", str(DEFAULT_TEMPLATE_MATCHING)))


def get_template_crop_size() -> int:
    return int(os.getenv("TEMPLATE_CROP_SIZE", str(DEFAULT_TEMPLATE_CROP_SIZE)))


def match_template(
    screenshot: Image.Image,
    template_path: Path,
    matching: float = DEFAULT_TEMPLATE_MATCHING,
) -> Optional[tuple[int, int, Region]]:
    """
    Find template on screenshot using BotCity cv2find.

    Returns (center_x, center_y, region) or None if no match.
    """
    if not template_path.exists():
        logger.warning("[Template] Template file not found: %s", template_path)
        return None

    logger.info(
        "[Template] Searching for %s on %dx%d screenshot (matching=%.2f)",
        template_path,
        screenshot.width,
        screenshot.height,
        matching,
    )

    try:
        matches = cv2find.locate_all_opencv(
            needle_image=str(template_path),
            haystack_image=screenshot,
            confidence=matching,
        )
        box = next(matches, None)
    except Exception as exc:
        logger.warning("[Template] Match failed: %s", exc)
        return None

    if box is None:
        logger.warning("[Template] No match found for %s", template_path)
        return None

    cx = box.left + box.width // 2
    cy = box.top + box.height // 2
    region = Region(
        x1=box.left,
        y1=box.top,
        x2=box.left + box.width,
        y2=box.top + box.height,
    )
    logger.info(
        "[Template] Match found at box=(%d,%d,%d,%d) center=(%d,%d)",
        box.left, box.top, box.width, box.height, cx, cy,
    )
    return cx, cy, region


def try_template_fallback(
    screenshot: Image.Image,
    query: str,
    save_annotated_to: Optional[Path] = None,
) -> Optional[tuple[int, int]]:
    """
    Attempt last-resort template matching after VLM grounding fails.

    Returns (x, y) on success, None otherwise.
    """
    template_path = get_template_path()
    matching = get_template_matching()
    result = match_template(screenshot, template_path, matching=matching)
    if result is None:
        return None

    cx, cy, region = result

    if not (0 <= cx < screenshot.width and 0 <= cy < screenshot.height):
        logger.warning(
            "[Template] Matched coordinates (%d,%d) out of screen bounds.",
            cx, cy,
        )
        return None

    logger.info("[Template] Last-resort match SUCCESS: %r → screen=(%d,%d)", query, cx, cy)

    if save_annotated_to is not None:
        from src.grounding.annotator import save_annotated

        save_annotated(
            img=screenshot,
            region=region,
            center=(cx, cy),
            label=query,
            path=save_annotated_to,
            stage="TemplateMatch",
        )

    return cx, cy
