"""
Notepad-specific automation workflow.
Handles open → type → save → close using mouse.py + pygetwindow.
"""

from __future__ import annotations

import os
import time
from pathlib import Path

import pygetwindow as gw

from src.automation.mouse import click, double_click, hotkey, press, type_text
from src.utils.logger import get_logger

logger = get_logger(__name__)

# Seconds to wait for Notepad to appear after double-clicking the icon.
_LAUNCH_WAIT = float(os.getenv("NOTEPAD_LAUNCH_WAIT", "2.0"))

# Save dialog: extra time for the dialog to fully render before typing.
_DIALOG_WAIT = 0.8

# Output directory on the user's Desktop.
_OUTPUT_DIR = Path.home() / "Desktop" / "tjm-project"


def _wait_for_notepad(timeout: float = 5.0) -> None:
    """Block until a Notepad window appears or timeout is reached."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        windows = gw.getWindowsWithTitle("Notepad")
        if windows:
            windows[0].activate()
            logger.debug("Notepad window found and activated.")
            return
        time.sleep(0.3)
    raise TimeoutError(f"Notepad did not open within {timeout}s.")


def open_notepad(x: int, y: int) -> None:
    """
    Double-click the desktop icon at (x, y) and wait for Notepad to open.
    Raises TimeoutError if the window never appears.
    """
    logger.info("Opening Notepad via icon at (%d, %d)", x, y)
    double_click(x, y)
    time.sleep(_LAUNCH_WAIT)
    _wait_for_notepad()
    logger.info("Notepad is open.")


def type_content(title: str, body: str) -> None:
    """Type the post content into the active Notepad window."""
    content = f"Title: {title}\n\n{body}"
    logger.info("Typing content (%d chars) into Notepad.", len(content))
    type_text(content)


def save_file(post_id: int) -> None:
    """
    Save the current Notepad document as post_{post_id}.txt inside
    Desktop\\tjm-project\\ using the Save As dialog.
    """
    filename = f"post_{post_id}.txt"
    logger.info("Saving file: %s → %s", filename, _OUTPUT_DIR)

    # Ensure the output directory exists on the local machine.
    _OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    # Open Save As dialog.
    hotkey("ctrl", "shift", "s")
    time.sleep(_DIALOG_WAIT)

    # If Ctrl+Shift+S doesn't work (older Notepad), fall back to Ctrl+S.
    # On a fresh unsaved document both will open Save As.
    save_as_windows = [w for w in gw.getAllWindows() if "Save As" in w.title or "Save" in w.title]
    if not save_as_windows:
        hotkey("ctrl", "s")
        time.sleep(_DIALOG_WAIT)

    # Type the full absolute path so Windows navigates directly to the folder.
    full_path = str(_OUTPUT_DIR / filename)
    type_text(full_path)
    time.sleep(0.3)
    press("enter")
    time.sleep(0.5)

    # Handle overwrite confirmation if the file already exists.
    confirm = [w for w in gw.getAllWindows() if "Confirm" in w.title or "Replace" in w.title]
    if confirm:
        logger.debug("Overwrite confirmation dialog detected — confirming.")
        press("enter")
        time.sleep(0.3)

    logger.info("File saved: %s", full_path)


def close_notepad() -> None:
    """Close the active Notepad window."""
    logger.info("Closing Notepad.")
    hotkey("alt", "f4")
    time.sleep(0.5)

    # Dismiss any unsaved-changes prompt (shouldn't appear after save, but be safe).
    prompt = [w for w in gw.getAllWindows() if "Notepad" in w.title and "save" in w.title.lower()]
    if prompt:
        logger.debug("Unsaved changes prompt detected — discarding.")
        press("tab")
        press("enter")
