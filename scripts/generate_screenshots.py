"""
Generate the 3 required annotated deliverable screenshots.

Usage (run once per icon position — move the icon, then run):

  uv run python scripts/generate_screenshots.py top_left
  uv run python scripts/generate_screenshots.py bottom_right
  uv run python scripts/generate_screenshots.py center

Each run:
  1. Captures the current desktop
  2. Runs the two-stage VLM grounding pipeline
  3. Saves an annotated screenshot to screenshots/<position>.png

Before running each command, physically move the Notepad desktop shortcut
to the indicated region of the screen.
"""

from __future__ import annotations

import sys
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

# Allow running as a script from the repo root.
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.automation.screen import capture_desktop, save_screenshot
from src.grounding.defaults import get_grounding_query
from src.grounding.screenseeker import ground
from src.utils.logger import get_logger

logger = get_logger(__name__)

_QUERY = get_grounding_query()
_OUT_DIR = Path("screenshots")
_VALID_POSITIONS = ("top_left", "bottom_right", "center")


def main() -> None:
    if len(sys.argv) != 2 or sys.argv[1] not in _VALID_POSITIONS:
        print(
            f"Usage: uv run python scripts/generate_screenshots.py "
            f"[{'|'.join(_VALID_POSITIONS)}]"
        )
        sys.exit(1)

    position = sys.argv[1]
    raw_path = _OUT_DIR / f"raw_{position}.png"
    annotated_path = _OUT_DIR / f"annotated_{position}.png"

    print(f"\n{'─' * 60}")
    print(f"  Generating screenshot: {position}")
    print(f"  Make sure the Notepad icon is in the {position.replace('_', ' ')} area.")
    print(f"{'─' * 60}\n")

    print("Capturing desktop…")
    screenshot = capture_desktop()
    save_screenshot(screenshot, raw_path)
    print(f"  Raw screenshot saved → {raw_path}")

    print("Running two-stage VLM grounding…")
    try:
        x, y = ground(
            query=_QUERY,
            screenshot=screenshot,
            save_annotated_to=annotated_path,
        )
        print(f"\n  Grounding SUCCESS: ({x}, {y})")
        print(f"  Annotated screenshot saved → {annotated_path}")
    except RuntimeError as exc:
        print(f"\n  Grounding FAILED: {exc}")
        sys.exit(1)


if __name__ == "__main__":
    main()
