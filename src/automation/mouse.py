"""
Mouse and keyboard control via pyautogui.
All timings are tuned for Windows 10/11 at 1920x1080.
"""

from __future__ import annotations

import time

import pyautogui

from src.utils.logger import get_logger

logger = get_logger(__name__)

# Safety margin: pyautogui will raise FailSafeException if the mouse is moved
# to the top-left corner of the screen. Keep this enabled.
pyautogui.FAILSAFE = True

# Default inter-key delay for typewrite (seconds). Keeps keystrokes reliable.
_TYPE_INTERVAL = 0.02


def double_click(x: int, y: int, pause: float = 0.3) -> None:
    """Move to (x, y) and double-click. Used to launch desktop icons."""
    logger.debug("Double-clicking at (%d, %d)", x, y)
    pyautogui.doubleClick(x, y)
    time.sleep(pause)


def click(x: int, y: int, pause: float = 0.2) -> None:
    """Single left-click at (x, y)."""
    logger.debug("Clicking at (%d, %d)", x, y)
    pyautogui.click(x, y)
    time.sleep(pause)


def type_text(text: str, interval: float = _TYPE_INTERVAL) -> None:
    """
    Type a string character by character.
    Uses pyautogui.write for ASCII and pyautogui.hotkey for special chars
    so that newlines and Unicode are handled correctly.
    """
    logger.debug("Typing %d characters", len(text))
    # Split on newline so we can send Enter keystrokes explicitly,
    # which is more reliable than embedding \n in typewrite.
    lines = text.split("\n")
    for i, line in enumerate(lines):
        if line:
            pyautogui.write(line, interval=interval)
        if i < len(lines) - 1:
            pyautogui.press("enter")


def hotkey(*keys: str) -> None:
    """
    Press a key combination, e.g. hotkey('ctrl', 's') or hotkey('alt', 'f4').
    Accepts any number of key names supported by pyautogui.
    """
    logger.debug("Hotkey: %s", "+".join(keys))
    pyautogui.hotkey(*keys)
    time.sleep(0.2)


def press(key: str, pause: float = 0.2) -> None:
    """Press a single key by name (e.g. 'enter', 'escape', 'tab')."""
    logger.debug("Press: %s", key)
    pyautogui.press(key)
    time.sleep(pause)
