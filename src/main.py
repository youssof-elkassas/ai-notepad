"""
AI Notepad — main orchestrator.

Workflow (×10 posts):
  1. Fetch posts from JSONPlaceholder
  2. For each post:
     a. Capture desktop screenshot
     b. Check for blocking popups and dismiss them
     c. Ground the Notepad desktop icon → get (x, y)
     d. Open Notepad via double-click
     e. Type post content
     f. Save as post_{id}.txt in Desktop\\tjm-project\\
     g. Close Notepad
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

import pyautogui
from dotenv import load_dotenv

load_dotenv()

from src.api.posts import fetch_posts
from src.automation.mouse import hotkey, press
from src.automation.notepad import close_notepad, open_notepad, save_file, type_content
from src.automation.screen import capture_desktop, save_screenshot
from src.grounding.screenseeker import detect_popup, ground
from src.utils.logger import get_logger

logger = get_logger(__name__)

_SCREENSHOTS_DIR = Path("screenshots")
_NOTEPAD_QUERY = "Notepad desktop shortcut icon"


def _dismiss_popup(screenshot) -> None:
    """Check for a blocking dialog and dismiss it if present."""
    result = detect_popup(screenshot)
    if not result.get("has_popup"):
        return

    description = result.get("description", "unknown")
    dismiss_key = result.get("dismiss_key", "Escape")
    logger.warning("Popup detected: %s — dismissing with %s", description, dismiss_key)

    if dismiss_key == "Tab+Enter":
        press("tab")
        press("enter")
    elif dismiss_key in ("Enter", "Escape"):
        press(dismiss_key.lower())
    else:
        press("escape")

    time.sleep(0.5)


def main() -> None:
    logger.info("=" * 60)
    logger.info("AI Notepad — Vision-Based Desktop Automation")
    logger.info("=" * 60)

    # ── 1. Fetch posts ─────────────────────────────────────────────
    try:
        posts = fetch_posts(limit=10)
    except Exception as exc:
        logger.error("Failed to fetch posts: %s", exc)
        sys.exit(1)

    logger.info("Starting automation loop for %d posts.", len(posts))

    for i, post in enumerate(posts, start=1):
        post_id = post["id"]
        title = post["title"]
        body = post["body"]

        logger.info("─" * 50)
        logger.info("Post %d/%d  (id=%d): %s", i, len(posts), post_id, title)

        # ── 2a. Show desktop, then capture ────────────────────────
        # Press Win+D to minimize all windows so the VLM sees a clean
        # desktop with only icons — no terminal text to confuse Stage 1.
        pyautogui.hotkey("win", "d")
        time.sleep(1.0)
        screenshot = capture_desktop()
        save_screenshot(
            screenshot,
            _SCREENSHOTS_DIR / f"raw_post_{post_id:02d}.png",
        )

        # ── 2b. Dismiss any blocking popup ─────────────────────────
        _dismiss_popup(screenshot)

        # ── 2c. Ground the Notepad icon ────────────────────────────
        annotated_path = _SCREENSHOTS_DIR / f"grounded_post_{post_id:02d}.png"
        try:
            x, y = ground(
                query=_NOTEPAD_QUERY,
                screenshot=screenshot,
                save_annotated_to=annotated_path,
            )
        except RuntimeError as exc:
            logger.error("Grounding failed for post %d: %s — skipping.", post_id, exc)
            continue

        logger.info("Notepad icon grounded at (%d, %d)", x, y)

        # ── 2d–2g. Open → Type → Save → Close ─────────────────────
        try:
            open_notepad(x, y)
            type_content(title, body)
            save_file(post_id)
            close_notepad()
        except Exception as exc:
            logger.error("Automation error on post %d: %s", post_id, exc)
            # Best-effort cleanup: try to close any open Notepad window.
            try:
                hotkey("alt", "f4")
                time.sleep(0.5)
                press("tab")
                press("enter")
            except Exception:
                pass
            continue

        logger.info("Post %d saved successfully.", post_id)

    logger.info("=" * 60)
    logger.info("All done! Files saved to Desktop\\tjm-project\\")
    logger.info("=" * 60)


if __name__ == "__main__":
    main()
