"""
AI Notepad — main orchestrator.

Workflow (×10 posts):
  1. Fetch posts from JSONPlaceholder
  2. For each post:
     a. Win+D once → optional popup check/dismiss (same desktop view)
     b. Capture desktop (no second Win+D) → ground Notepad icon → (x, y)
     c. Open Notepad via double-click
     d. Type post content
     e. Save as post_{id}.txt in Desktop\\tjm-project\\
     f. Close Notepad
"""

from __future__ import annotations

import os
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
from src.grounding.defaults import get_grounding_query
from src.grounding.screenseeker import (
    detect_popup,
    get_cached_coords,
    ground_and_cache,
    invalidate_cache,
    is_coord_cache_enabled,
    set_cached_coords,
)
from src.grounding.template_match import (
    is_template_fallback_enabled,
    try_template_fallback,
)
from src.utils.logger import get_logger

logger = get_logger(__name__)

_SCREENSHOTS_DIR = Path("screenshots")
_MAX_LAUNCH_ATTEMPTS = 3
_SHOW_DESKTOP_WAIT = 1.0
_CHECK_POPUPS = os.getenv("CHECK_POPUPS", "true").lower() in ("1", "true", "yes", "on")


def _move_mouse_top_center() -> None:
    """Park the cursor at the top-center of the screen (away from desktop icons)."""
    screen_w, _screen_h = pyautogui.size()
    x, y = screen_w // 2, 0
    logger.debug("Moving mouse to top-center (%d, %d)", x, y)
    pyautogui.moveTo(x, y)
    time.sleep(0.1)


def _capture_desktop():
    """Capture the desktop; with COORD_CACHE=false, park cursor at top-center first."""
    if not is_coord_cache_enabled():
        _move_mouse_top_center()
    return capture_desktop()


def _show_desktop_and_capture():
    """Minimize all windows and capture the desktop."""
    pyautogui.hotkey("win", "d")
    time.sleep(_SHOW_DESKTOP_WAIT)
    return _capture_desktop()


def _dismiss_popup(screenshot) -> bool:
    """Check for a blocking dialog and dismiss it if present.

    Returns True if a popup was dismissed (caller may need a fresh capture).
    """
    result = detect_popup(screenshot)
    if not result.get("has_popup"):
        return False

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
    return True


def _log_run_summary(
    results: list[tuple[int, int, str, str]],
) -> None:
    """Log per-post outcomes. Each item is (index, post_id, status, detail)."""
    total = len(results)
    ok = sum(1 for _, _, status, _ in results if status == "SUCCESS")
    failed = total - ok

    logger.info("=" * 60)
    logger.info("Run summary — %d/%d succeeded, %d failed", ok, total, failed)
    logger.info("-" * 60)
    for index, post_id, status, detail in results:
        if status == "SUCCESS":
            logger.info("  Post %d (id=%d): SUCCESS", index, post_id)
        else:
            logger.info("  Post %d (id=%d): FAILED — %s", index, post_id, detail)
    logger.info("=" * 60)
    if ok:
        logger.info("Files saved to Desktop\\tjm-project\\")
    logger.info("=" * 60)


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
    if _CHECK_POPUPS:
        logger.info("Popup check enabled (set CHECK_POPUPS=false to skip).")
    else:
        logger.info("Popup check disabled.")
    if is_coord_cache_enabled():
        logger.info("Coord cache enabled (set COORD_CACHE=false to skip).")
    else:
        logger.info("Coord cache disabled — grounding every post.")

    results: list[tuple[int, int, str, str]] = []

    for i, post in enumerate(posts, start=1):
        post_id = post["id"]
        title = post["title"]
        body = post["body"]

        logger.info("─" * 50)
        logger.info("Post %d/%d  (id=%d): %s", i, len(posts), post_id, title)

        # ── 2a–2b. Show desktop once, optional popup check, then ground ─
        # Win+D is a toggle: a second press would restore windows (terminal,
        # IDE, etc.) before raw_post_*.png — so never call it twice here.
        screenshot = _show_desktop_and_capture()
        if _CHECK_POPUPS:
            save_screenshot(
                screenshot,
                _SCREENSHOTS_DIR / f"popup_post_{post_id:02d}.png",
            )
            if _dismiss_popup(screenshot):
                # Desktop should still be showing; capture again without Win+D.
                screenshot = _capture_desktop()

        save_screenshot(
            screenshot,
            _SCREENSHOTS_DIR / f"raw_post_{post_id:02d}.png",
        )

        # ── 2c–2d. Launch Notepad (cached coords first, ground on failure) ──
        annotated_path = _SCREENSHOTS_DIR / f"grounded_post_{post_id:02d}.png"
        launched = False
        grounding_query = get_grounding_query()
        cached = get_cached_coords(grounding_query)
        fail_reason = "could not open Notepad"

        if cached is not None:
            x, y = cached
            logger.info("Cache HIT — trying cached coords (%d, %d)", x, y)
            try:
                open_notepad(x, y)
                launched = True
            except TimeoutError:
                logger.warning("Cached coords did not open Notepad — re-grounding…")
                invalidate_cache(grounding_query)

        if not launched:
            for launch_attempt in range(1, _MAX_LAUNCH_ATTEMPTS + 1):
                try:
                    x, y = ground_and_cache(
                        query=grounding_query,
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
                    invalidate_cache(grounding_query)
                    screenshot = _show_desktop_and_capture()
                    fail_reason = "Notepad did not open after grounding retries"
                except RuntimeError as exc:
                    logger.error("Grounding failed: %s — skipping post.", exc)
                    fail_reason = f"grounding failed: {exc}"
                    break

        # VLM may return coords that miss the icon; template match after failed opens.
        if not launched and is_template_fallback_enabled():
            logger.info(
                "Launch retries exhausted — trying BotCity template fallback…"
            )
            screenshot = _show_desktop_and_capture()
            template_coords = try_template_fallback(
                screenshot,
                grounding_query,
                save_annotated_to=annotated_path,
            )
            if template_coords is not None:
                x, y = template_coords
                set_cached_coords(grounding_query, x, y)
                try:
                    open_notepad(x, y)
                    launched = True
                except TimeoutError:
                    logger.error(
                        "Template match at (%d, %d) did not open Notepad.", x, y
                    )
                    fail_reason = "template match did not open Notepad"
            else:
                fail_reason = "template match found no icon"

        if not launched:
            logger.error(
                "Could not open Notepad after %d attempts — skipping post.",
                _MAX_LAUNCH_ATTEMPTS,
            )
            results.append((i, post_id, "FAILED", fail_reason))
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
            results.append((i, post_id, "FAILED", f"automation error: {exc}"))
            continue

        logger.info("Post %d saved successfully.", post_id)
        results.append((i, post_id, "SUCCESS", "saved"))

    _log_run_summary(results)


if __name__ == "__main__":
    main()
