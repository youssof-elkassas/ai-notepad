"""
Test script for the ScreenSeekeR grounding engine.

Usage:
    uv run python scripts/test_grounding.py
    uv run python scripts/test_grounding.py "Trash icon"
    uv run python scripts/test_grounding.py "Notepad desktop shortcut icon"

What it does:
1. Takes a screenshot of your current desktop
2. Runs the two-stage VLM grounding for the given query
3. Saves two files to screenshots/:
   - screenshot_raw.png        — the original desktop capture
   - screenshot_grounded.png   — annotated with bounding box + crosshair
4. Prints the detected (x, y) coordinates

Requires GOOGLE_API_KEY in .env (free at https://aistudio.google.com)
"""

import sys
import time
from pathlib import Path

# Allow running from repo root
sys.path.insert(0, str(Path(__file__).parent.parent))

from dotenv import load_dotenv
load_dotenv()

import pyautogui
from src.automation.screen import capture_desktop, save_screenshot
from src.grounding.defaults import get_grounding_query
from src.grounding.screenseeker import ground
from src.utils.logger import get_logger

logger = get_logger("test_grounding")

SCREENSHOTS_DIR = Path(__file__).parent.parent / "screenshots"
SCREENSHOTS_DIR.mkdir(exist_ok=True)

_SHOW_DESKTOP_WAIT = 1.0  # seconds to let window-minimize animation finish


def main():
    query = " ".join(sys.argv[1:]) if len(sys.argv) > 1 else get_grounding_query()

    print(f"\n{'─'*60}")
    print(f"  ScreenSeekeR Grounding Test")
    print(f"  Query: {query!r}")
    print(f"{'─'*60}\n")

    # Show desktop before capturing so open terminal windows don't confuse the VLM.
    print("🖥️  Showing desktop (Win+D) — minimizing all windows…")
    pyautogui.hotkey("win", "d")
    time.sleep(_SHOW_DESKTOP_WAIT)

    # Step 1: capture desktop
    print("📸  Capturing desktop screenshot…")
    screenshot = capture_desktop()
    raw_path = SCREENSHOTS_DIR / "screenshot_raw.png"
    save_screenshot(screenshot, raw_path)
    print(f"    Saved raw screenshot → {raw_path}")
    print(f"    Resolution: {screenshot.width}×{screenshot.height}\n")

    # Step 2: ground the target
    grounded_path = SCREENSHOTS_DIR / "screenshot_grounded.png"
    print("🔍  Running two-stage VLM grounding…")
    print("    Stage 1: full screenshot → Gemini 2.5 Flash → coarse bounding box")
    print("    Stage 2: cropped region  → Gemini 2.5 Flash → precise center\n")

    try:
        x, y = ground(
            query=query,
            screenshot=screenshot,
            save_annotated_to=grounded_path,
        )
        print(f"\n✅  Grounding SUCCESS")
        print(f"    Element:     {query!r}")
        print(f"    Coordinates: x={x}, y={y}")
        print(f"    Annotated screenshot → {grounded_path}")
        print(f"\n    Open screenshots/screenshot_grounded.png to see the result.")

    except RuntimeError as e:
        print(f"\n❌  Grounding FAILED: {e}")
        print("    Check that your GOOGLE_API_KEY is set in .env")
        print("    and that the element is visible on screen.")
        sys.exit(1)


if __name__ == "__main__":
    main()
