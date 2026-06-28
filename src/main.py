"""
AI Notepad — main orchestrator.

Workflow (×10 posts):
  1. Fetch posts from JSONPlaceholder
  2. For each post:
     a. Capture screenshot → check/dismiss popups
     b. Capture fresh screenshot → ground Notepad icon → get (x, y)
     c. Open Notepad via double-click
     d. Type post content
     e. Save as post_{id}.txt in Desktop\\tjm-project\\
     f. Close Notepad
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
from src.grounding.screenseeker import (
    detect_popup,
    get_cached_coords,
    ground_and_cache,
    invalidate_cache,
)
from src.utils.logger import get_logger

logger = get_logger(__name__)

_SCREENSHOTS_DIR = Path("screenshots")
_NOTEPAD_QUERY = "Notepad desktop shortcut icon"
_MAX_LAUNCH_ATTEMPTS = 3
_SHOW_DESKTOP_WAIT = 1.0


def _show_desktop_and_capture():
    """Minimize all windows and capture the desktop."""
    pyautogui.hotkey("win", "d")
    time.sleep(_SHOW_DESKTOP_WAIT)
    return capture_desktop()


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

        # ── 2a. Popup check (first screenshot) ─────────────────────
        popup_screenshot = _show_desktop_and_capture()
        save_screenshot(
            popup_screenshot,
            _SCREENSHOTS_DIR / f"popup_post_{post_id:02d}.png",
        )
        _dismiss_popup(popup_screenshot)

        # ── 2b. Fresh screenshot for grounding / launch ────────────
        screenshot = _show_desktop_and_capture()
        save_screenshot(
            screenshot,
            _SCREENSHOTS_DIR / f"raw_post_{post_id:02d}.png",
        )

        # ── 2c–2d. Launch Notepad (cached coords first, ground on failure) ──
        annotated_path = _SCREENSHOTS_DIR / f"grounded_post_{post_id:02d}.png"
        launched = False
        cached = get_cached_coords(_NOTEPAD_QUERY)

        if cached is not None:
            x, y = cached
            logger.info("Cache HIT — trying cached coords (%d, %d)", x, y)
            try:
                open_notepad(x, y)
                launched = True
            except TimeoutError:
                logger.warning("Cached coords did not open Notepad — re-grounding…")
                invalidate_cache(_NOTEPAD_QUERY)

        if not launched:
            for launch_attempt in range(1, _MAX_LAUNCH_ATTEMPTS + 1):
                try:
                    x, y = ground_and_cache(
                        query=_NOTEPAD_QUERY,
                        screenshot=screenshot,
                        save_annotated_to=annotated_path,
                    )
                    logger.info("Notepad icon grounded at (%d, %d)", x, y)
                    open_notepad(x, y)
                    launched = True
                    break
                except TimeoutError:
                    logger.warning(
                        "Notepad did not open (attempt %d/%d) — re-grounding…",
                        launch_attempt,
                        _MAX_LAUNCH_ATTEMPTS,
                    )
                    invalidate_cache(_NOTEPAD_QUERY)
                    screenshot = _show_desktop_and_capture()
                except RuntimeError as exc:
                    logger.error("Grounding failed: %s — skipping post.", exc)
                    break

        if not launched:
            logger.error(
                "Could not open Notepad after %d attempts — skipping post.",
                _MAX_LAUNCH_ATTEMPTS,
            )
            continue

        # ── 2e–2g. Type → Save → Close ─────────────────────────────
        try:
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
