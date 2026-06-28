"""
Notepad-specific automation workflow.
Handles open → type → save → close using mouse.py + pygetwindow.
"""

from __future__ import annotations

import os
import subprocess
import time
from pathlib import Path

import pygetwindow as gw

from src.automation.mouse import double_click, hotkey, press, type_text
from src.utils.logger import get_logger

logger = get_logger(__name__)

# Seconds to wait for Notepad to appear after double-clicking the icon.
_LAUNCH_WAIT = float(os.getenv("NOTEPAD_LAUNCH_WAIT", "2.0"))

# Vertical offset applied to grounded coords — VLM often targets the icon
# center between the graphic and label; nudge downward onto the clickable icon.
_CLICK_OFFSET_Y = int(os.getenv("NOTEPAD_CLICK_OFFSET_Y", "20"))

# Save dialog: extra time for the dialog to fully render before typing.
_DIALOG_WAIT = 0.8

# Output directory on the user's Desktop.
_OUTPUT_DIR = Path.home() / "Desktop" / "tjm-project"

# Window titles that contain "notepad" as a substring but are NOT the app.
_TITLE_FALSE_POSITIVES = (
    "powershell",
    "command prompt",
    "windows powershell",
    "cursor",
    "visual studio code",
    "ai-notepad",
    "python",
    "cmd.exe",
    "terminal",
)


def _notepad_process_count() -> int:
    """Return the number of running notepad.exe processes."""
    try:
        result = subprocess.run(
            ["tasklist", "/FI", "IMAGENAME eq notepad.exe", "/NH"],
            capture_output=True,
            text=True,
            check=False,
        )
    except OSError as exc:
        logger.warning("Could not query notepad.exe processes: %s", exc)
        return 0

    return sum(
        1
        for line in result.stdout.splitlines()
        if "notepad.exe" in line.lower()
    )


def _is_notepad_window_title(title: str) -> bool:
    """Return True if the window title looks like the Notepad application."""
    t = title.strip()
    if not t:
        return False

    lower = t.lower()
    if any(marker in lower for marker in _TITLE_FALSE_POSITIVES):
        return False

    if lower == "notepad" or lower.endswith(" - notepad"):
        return True

    # Windows 11 Notepad often opens with title "Untitled".
    if lower == "untitled":
        return True

    return False


def _get_notepad_windows() -> list[gw.Win32Window]:
    """Return windows that appear to be Notepad, excluding false positives."""
    return [w for w in gw.getAllWindows() if _is_notepad_window_title(w.title or "")]


def _activate_notepad_window() -> None:
    """Bring a Notepad window to the foreground."""
    windows = _get_notepad_windows()
    if not windows:
        raise RuntimeError("Notepad is not open.")

    windows[-1].activate()
    time.sleep(0.3)

    active = gw.getActiveWindow()
    if active is None or not _is_notepad_window_title(active.title or ""):
        raise RuntimeError("Notepad is open but could not be focused.")


def _wait_for_new_notepad(before_count: int, timeout: float = 10.0) -> None:
    """
    Block until a new notepad.exe process appears or timeout is reached.

    Uses process count instead of window title substring matching so we do not
    false-positive on terminals whose path contains 'ai-notepad'.
    """
    deadline = time.time() + timeout
    while time.time() < deadline:
        if _notepad_process_count() > before_count:
            _activate_notepad_window()
            logger.debug("New Notepad process detected.")
            return
        time.sleep(0.3)

    raise TimeoutError(f"Notepad did not open within {timeout}s.")


def is_notepad_open() -> bool:
    """Return True if at least one Notepad process is running."""
    return _notepad_process_count() > 0


def open_notepad(x: int, y: int) -> None:
    """
    Double-click the desktop icon at (x, y) and wait for Notepad to open.
    Raises TimeoutError if the window never appears.
    """
    click_y = y + _CLICK_OFFSET_Y
    logger.info(
        "Opening Notepad via icon at (%d, %d) with Y offset +%d → (%d, %d)",
        x, y, _CLICK_OFFSET_Y, x, click_y,
    )

    before_count = _notepad_process_count()
    double_click(x, click_y)
    time.sleep(_LAUNCH_WAIT)
    _wait_for_new_notepad(before_count)
    logger.info("Notepad is open.")


def type_content(title: str, body: str) -> None:
    """Type the post content into the active Notepad window."""
    if not is_notepad_open():
        raise RuntimeError("Cannot type content — Notepad is not open.")

    _activate_notepad_window()

    content = f"Title: {title}\n\n{body}"
    logger.info("Typing content (%d chars) into Notepad.", len(content))
    type_text(content)


def save_file(post_id: int) -> None:
    """
    Save the current Notepad document as post_{post_id}.txt inside
    Desktop\\tjm-project\\ using the Save As dialog.
    """
    if not is_notepad_open():
        raise RuntimeError("Cannot save — Notepad is not open.")

    _activate_notepad_window()

    filename = f"post_{post_id}.txt"
    full_path = _OUTPUT_DIR / filename
    logger.info("Saving file: %s → %s", filename, _OUTPUT_DIR)

    _OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    hotkey("ctrl", "shift", "s")
    time.sleep(_DIALOG_WAIT)

    save_as_windows = [
        w for w in gw.getAllWindows()
        if "Save As" in w.title or "Save" in w.title
    ]
    if not save_as_windows:
        hotkey("ctrl", "s")
        time.sleep(_DIALOG_WAIT)

    type_text(str(full_path))
    time.sleep(0.3)
    press("enter")
    time.sleep(0.5)

    confirm = [
        w for w in gw.getAllWindows()
        if "Confirm" in w.title or "Replace" in w.title
    ]
    if confirm:
        logger.debug("Overwrite confirmation dialog detected — confirming.")
        press("enter")
        time.sleep(0.3)

    if not full_path.exists():
        raise RuntimeError(f"Save failed — file not found on disk: {full_path}")

    logger.info("File saved: %s", full_path)


def close_notepad() -> None:
    """Close the active Notepad window."""
    if not is_notepad_open():
        logger.warning("close_notepad called but Notepad is not running.")
        return

    _activate_notepad_window()
    logger.info("Closing Notepad.")
    hotkey("alt", "f4")
    time.sleep(0.5)

    prompt = [
        w for w in gw.getAllWindows()
        if "Notepad" in w.title and "save" in w.title.lower()
    ]
    if prompt:
        logger.debug("Unsaved changes prompt detected — discarding.")
        press("tab")
        press("enter")
