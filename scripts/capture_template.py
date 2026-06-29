"""
Capture a template image for BotCity template-matching fallback.

Run once on the Windows test machine (1920x1080, Notepad shortcut on desktop):

    uv run python scripts/capture_template.py

Steps:
  1. Win+D to show desktop
  2. VLM grounding for the current GROUNDING_QUERY
  3. Crop a square around the grounded center
  4. Save to resources/templates/notepad_shortcut.png (or TEMPLATE_IMAGE_PATH)
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import pyautogui
from dotenv import load_dotenv

load_dotenv()

from src.automation.screen import capture_desktop, save_screenshot
from src.grounding.defaults import get_grounding_query
from src.grounding.screenseeker import ground
from src.grounding.template_match import get_template_crop_size, get_template_path
from src.utils.logger import get_logger

logger = get_logger(__name__)

_SHOW_DESKTOP_WAIT = 1.0


def main() -> None:
    query = get_grounding_query()
    crop_size = get_template_crop_size()
    out_path = get_template_path()

    print(f"\n{'─' * 60}")
    print("  Template Capture")
    print(f"  Query:     {query!r}")
    print(f"  Crop size: {crop_size}x{crop_size}")
    print(f"  Output:    {out_path}")
    print(f"{'─' * 60}\n")

    print("Showing desktop (Win+D)…")
    pyautogui.hotkey("win", "d")
    time.sleep(_SHOW_DESKTOP_WAIT)

    print("Capturing screenshot and running VLM grounding…")
    screenshot = capture_desktop()
    x, y = ground(query=query, screenshot=screenshot)

    half = crop_size // 2
    left = max(0, x - half)
    top = max(0, y - half)
    right = min(screenshot.width, left + crop_size)
    bottom = min(screenshot.height, top + crop_size)
    # Re-adjust if clamped at screen edge.
    left = max(0, right - crop_size)
    top = max(0, bottom - crop_size)

    crop = screenshot.crop((left, top, right, bottom))
    out_path.parent.mkdir(parents=True, exist_ok=True)
    save_screenshot(crop, out_path)

    print(f"\nTemplate saved → {out_path}")
    print(f"Grounded center: ({x}, {y})")
    print(f"Crop region: ({left}, {top}) – ({right}, {bottom})")
    print("\nCommit this file to the repo so template fallback works on other machines.")


if __name__ == "__main__":
    main()
