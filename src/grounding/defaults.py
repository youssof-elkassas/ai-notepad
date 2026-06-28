"""Default grounding query and visual description for VLM prompts."""

from __future__ import annotations

import os

from dotenv import load_dotenv

load_dotenv()

DEFAULT_GROUNDING_QUERY = "Notepad desktop shortcut icon"

DEFAULT_VISUAL_DESCRIPTION = """\
- A small Windows desktop shortcut icon, approximately 32-48 pixels wide.
- The Notepad icon shows a notepad or document with horizontal text lines, \
typically in blue/white colors or a pencil-and-paper illustration.
- It has a short text label directly underneath it reading "Notepad".
- It sits on the desktop surface (NOT inside the taskbar at the very bottom).
- It could be ANYWHERE in the image — do not assume any particular location."""


def get_grounding_query() -> str:
    return os.getenv("GROUNDING_QUERY", DEFAULT_GROUNDING_QUERY)


def get_visual_description() -> str:
    raw = os.getenv("GROUNDING_VISUAL_DESCRIPTION")
    if raw is None:
        return DEFAULT_VISUAL_DESCRIPTION
    return raw.replace("\\n", "\n")
