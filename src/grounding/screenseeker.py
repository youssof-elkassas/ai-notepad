"""
ScreenSeekeR — two-stage cascaded VLM grounding engine.

Inspired by ScreenSpot-Pro / ScreenSeekeR (arXiv:2504.07981):
  Stage 1 (Planner):  Full screenshot → MLLM → coarse bounding box
  Stage 2 (Grounder): Cropped region  → MLLM → precise center (x, y)

The system is provider-agnostic: set LLM_PROVIDER=gemini (default, free)
or LLM_PROVIDER=openai (paid fallback) in .env.
"""

from __future__ import annotations

import json
import os
import re
import time
from pathlib import Path
from typing import Optional

from PIL import Image
from dotenv import load_dotenv

from src.automation.screen import Region, crop_region, image_to_base64
from src.utils.logger import get_logger

load_dotenv()

logger = get_logger(__name__)

# ── Config ────────────────────────────────────────────────────────────────────
_PROVIDER = os.getenv("LLM_PROVIDER", "gemini").lower()
_GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")
_OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4o")
_MAX_RETRIES = int(os.getenv("MAX_GROUNDING_RETRIES", "3"))

# ── Prompts ───────────────────────────────────────────────────────────────────
_STAGE1_PROMPT = """You are a GUI grounding agent analyzing a full Windows desktop screenshot \
(1920×1080 pixels).

Your task: locate the UI element described as: "{query}"

Visual description of the target:
- A small Windows desktop shortcut icon, approximately 32-48 pixels wide.
- The Notepad icon shows a notepad or document with horizontal text lines, typically \
in blue/white colors or a pencil-and-paper illustration.
- It has a short text label directly underneath it, reading "Notepad".
- It sits on the desktop surface (NOT inside the taskbar at the very bottom of the screen).
- It could be ANYWHERE on the desktop: top-left corner, top-right corner, bottom-left, \
bottom-right, or center — do not assume any particular location.

Instructions:
- Carefully scan the ENTIRE desktop, including all four corners and edges, before answering.
- Look for small icon-sized elements (30-60 pixels) with a label underneath.
- Do NOT guess or default to the center of the screen if you are unsure.
- If you genuinely cannot find the element anywhere, return all zeros.

Return ONLY valid JSON with this exact structure:
{{"x1": <int>, "y1": <int>, "x2": <int>, "y2": <int>}}

Where x1,y1 is the top-left corner and x2,y2 is the bottom-right corner of the bounding \
box (pixel coordinates: x in 0-1920, y in 0-1080).

Rules:
- Return ONLY the JSON, no explanation.
- If you cannot find the element, return {{"x1": 0, "y1": 0, "x2": 0, "y2": 0}}"""

_STAGE2_PROMPT = """You are a GUI grounding agent analyzing a cropped screenshot region.

Your task: pinpoint the exact center pixel of the element described as: "{query}"

Visual description of the target element:
- It is a small desktop shortcut icon (approximately 32-48 pixels wide).
- The Notepad icon looks like a small notepad or document with horizontal lines, \
typically blue/white or a pencil-and-paper icon on a Windows desktop.
- It has a text label underneath it, usually reading "Notepad".
- It may be surrounded by other desktop icons — pick only the one that best matches \
the description.

The image you are analyzing is exactly {width} pixels wide and {height} pixels tall.

Return ONLY valid JSON with this exact structure:
{{"x": <int>, "y": <int>}}

Where x is a pixel column (0 to {width_max}) and y is a pixel row (0 to {height_max}) \
within THIS image — not the original full screen.

Rules:
- x must be an integer between 0 and {width_max} (inclusive).
- y must be an integer between 0 and {height_max} (inclusive).
- Always return your best estimate of the element's center, even if you are not \
100% certain. Only return {{"x": -1, "y": -1}} if there is absolutely no desktop \
icon visible anywhere in this image.
- Return ONLY the JSON, no explanation."""

_DIRECT_PROMPT = """You are a GUI grounding agent. Look carefully at this full Windows desktop \
screenshot (1920×1080 pixels).

Find and return the exact center pixel of: "{query}"

Visual description:
- A small Windows desktop shortcut icon (32-48 pixels wide).
- The Notepad icon shows a notepad/document with horizontal lines, typically blue/white or \
a pencil-and-paper illustration.
- It has a text label underneath reading "Notepad".
- It is on the desktop surface — NOT in the taskbar at the bottom of the screen.
- It can be anywhere: top-left, top-right, bottom-left, bottom-right, or center.

Scan every corner and edge of the screen carefully.

Return ONLY valid JSON:
{{"x": <int>, "y": <int>}}

Where x (0-1920) and y (0-1080) are the center pixel of the element in the full screenshot.
Only return {{"x": -1, "y": -1}} if the element is completely absent.
Return ONLY the JSON, no explanation."""

_POPUP_PROMPT = """You are a GUI agent. Analyze this screenshot.

Is there any dialog box, popup, alert, or modal window blocking the main UI?

Return ONLY valid JSON:
{{"has_popup": <bool>, "description": "<what it says>", "dismiss_key": "<Enter|Escape|Tab+Enter|none>"}}

Return ONLY the JSON, no explanation."""


# ── VLM client factory ────────────────────────────────────────────────────────

def _call_gemini(prompt: str, img: Image.Image) -> str:
    """Send image + prompt to Gemini and return raw text response."""
    import io
    from google import genai
    from google.genai import types

    client = genai.Client(api_key=os.environ["GOOGLE_API_KEY"])

    buf = io.BytesIO()
    img.save(buf, format="PNG")
    img_bytes = buf.getvalue()

    response = client.models.generate_content(
        model=_GEMINI_MODEL,
        contents=[
            types.Part.from_bytes(data=img_bytes, mime_type="image/png"),
            types.Part.from_text(text=prompt),
        ],
        config=types.GenerateContentConfig(
            response_mime_type="application/json",
            temperature=0.0,
        ),
    )
    return response.text


def _call_openai(prompt: str, img: Image.Image) -> str:
    """Send image + prompt to OpenAI GPT-4o and return raw text response."""
    from openai import OpenAI

    client = OpenAI(api_key=os.environ["OPENAI_API_KEY"])
    b64 = image_to_base64(img, fmt="PNG")

    response = client.chat.completions.create(
        model=_OPENAI_MODEL,
        response_format={"type": "json_object"},
        temperature=0.0,
        messages=[
            {
                "role": "user",
                "content": [
                    {
                        "type": "image_url",
                        "image_url": {"url": f"data:image/png;base64,{b64}"},
                    },
                    {"type": "text", "text": prompt},
                ],
            }
        ],
    )
    return response.choices[0].message.content


def _call_vlm(prompt: str, img: Image.Image) -> str:
    """Route to the configured VLM provider."""
    if _PROVIDER == "openai":
        return _call_openai(prompt, img)
    return _call_gemini(prompt, img)


# ── JSON parsing ──────────────────────────────────────────────────────────────

def _parse_json(text: str) -> dict:
    """Extract and parse JSON from VLM response, handling markdown fences."""
    text = text.strip()
    # Strip markdown code fences if present
    text = re.sub(r"^```(?:json)?\s*", "", text)
    text = re.sub(r"\s*```$", "", text)
    return json.loads(text)


# ── Core grounding ────────────────────────────────────────────────────────────

def _stage1_coarse(screenshot: Image.Image, query: str) -> Optional[Region]:
    """
    Stage 1 — Planner: ask VLM for a coarse bounding box on the full screenshot.
    Returns a Region or None if the element was not found / response invalid.
    """
    prompt = _STAGE1_PROMPT.format(query=query)
    logger.info("[Stage 1] Sending full screenshot to VLM for: %r", query)

    raw = _call_vlm(prompt, screenshot)
    logger.debug("[Stage 1] Raw response: %s", raw)

    data = _parse_json(raw)
    x1, y1, x2, y2 = data["x1"], data["y1"], data["x2"], data["y2"]

    if x1 == 0 and y1 == 0 and x2 == 0 and y2 == 0:
        logger.warning("[Stage 1] VLM reported element not found.")
        return None

    w, h = screenshot.size
    region = Region(
        x1=max(0, x1),
        y1=max(0, y1),
        x2=min(w, x2),
        y2=min(h, y2),
    )
    logger.info("[Stage 1] Coarse region: %s", region)
    return region


def _stage2_fine(
    screenshot: Image.Image,
    region: Region,
    query: str,
) -> Optional[tuple[int, int]]:
    """
    Stage 2 — Grounder: crop to the Stage 1 region and pinpoint the exact center.
    Returns (screen_x, screen_y) or None if not found.
    """
    padded = region.padded(pct=0.20, screen_w=screenshot.width, screen_h=screenshot.height)
    crop = crop_region(screenshot, padded)

    prompt = _STAGE2_PROMPT.format(
        query=query,
        width=crop.width,
        height=crop.height,
        width_max=crop.width - 1,
        height_max=crop.height - 1,
    )
    logger.info("[Stage 2] Sending %dx%d crop to VLM for: %r", crop.width, crop.height, query)

    raw = _call_vlm(prompt, crop)
    logger.debug("[Stage 2] Raw response: %s", raw)

    data = _parse_json(raw)
    lx, ly = data["x"], data["y"]

    if lx == -1 and ly == -1:
        # Stage 2 couldn't find the element in the crop — Stage 1 may have pointed
        # to the wrong region. Try a direct single-stage query on the full screenshot.
        logger.warning(
            "[Stage 2] VLM returned no center — trying direct full-screenshot query."
        )
        direct_prompt = _DIRECT_PROMPT.format(query=query)
        direct_raw = _call_vlm(direct_prompt, screenshot)
        logger.debug("[Direct] Raw response: %s", direct_raw)
        direct_data = _parse_json(direct_raw)
        dx, dy = direct_data["x"], direct_data["y"]

        if dx != -1 and dy != -1:
            # Apply same normalization check for 0-1000 scale
            if dx > screenshot.width or dy > screenshot.height:
                dx = int(dx / 1000 * screenshot.width)
                dy = int(dy / 1000 * screenshot.height)
            logger.info("[Direct] Found element at screen=(%d,%d)", dx, dy)
            return dx, dy

        # Last resort: use Stage 1 box center (better than failing entirely)
        sx = (region.x1 + region.x2) // 2
        sy = (region.y1 + region.y2) // 2
        logger.warning(
            "[Direct] Also failed — falling back to Stage 1 box center: screen=(%d,%d)",
            sx, sy,
        )
        return sx, sy

    # Gemini sometimes returns coordinates on a 0-1000 normalized scale instead of
    # pixel offsets. Detect this by checking if either value exceeds the crop bounds,
    # then rescale back to pixels.
    if lx > crop.width or ly > crop.height:
        logger.debug(
            "[Stage 2] Normalizing out-of-bounds response (%d,%d) from 0-1000 scale "
            "to %dx%d crop pixels.",
            lx, ly, crop.width, crop.height,
        )
        lx = int(lx / 1000 * crop.width)
        ly = int(ly / 1000 * crop.height)

    sx, sy = padded.map_local_to_screen(lx, ly)
    logger.info("[Stage 2] Fine center: local=(%d,%d) → screen=(%d,%d)", lx, ly, sx, sy)
    return sx, sy


# ── Public API ────────────────────────────────────────────────────────────────

def ground(
    query: str,
    screenshot: Image.Image,
    save_annotated_to: Optional[Path] = None,
) -> tuple[int, int]:
    """
    Locate a UI element on screen using two-stage cascaded VLM grounding.

    Args:
        query:              Plain-English description of the target element.
        screenshot:         Full-screen PIL Image.
        save_annotated_to:  If provided, save an annotated screenshot (bounding
                            box + crosshair) to this Path after successful grounding.

    Returns:
        (x, y) screen coordinates of the element center.

    Raises:
        RuntimeError: if grounding fails after all retries.
    """
    from src.grounding.annotator import save_annotated

    last_exc: Optional[Exception] = None

    for attempt in range(1, _MAX_RETRIES + 1):
        logger.info("Grounding attempt %d/%d for: %r", attempt, _MAX_RETRIES, query)
        try:
            region = _stage1_coarse(screenshot, query)
            if region is None:
                raise RuntimeError("Stage 1 returned no region.")

            center = _stage2_fine(screenshot, region, query)
            if center is None:
                raise RuntimeError("Stage 2 returned no center.")

            # Sanity-check: coordinates must be within screen bounds
            sx, sy = center
            if not (0 <= sx <= screenshot.width and 0 <= sy <= screenshot.height):
                raise ValueError(
                    f"Grounded coordinates ({sx},{sy}) out of screen bounds "
                    f"({screenshot.width}x{screenshot.height})."
                )

            logger.info("Grounding SUCCESS: %r → screen=(%d,%d)", query, sx, sy)

            # Save annotated screenshot if requested
            if save_annotated_to is not None:
                save_annotated(
                    img=screenshot,
                    region=region,
                    center=(sx, sy),
                    label=query,
                    path=save_annotated_to,
                    stage="ScreenSeekeR",
                )

            return sx, sy

        except Exception as exc:
            last_exc = exc
            logger.warning(
                "Grounding attempt %d failed: %s. Retrying in %.1fs…",
                attempt,
                exc,
                2 ** attempt,
            )
            time.sleep(2 ** attempt)

    raise RuntimeError(
        f"Grounding failed for {query!r} after {_MAX_RETRIES} attempts. "
        f"Last error: {last_exc}"
    )


def detect_popup(screenshot: Image.Image) -> dict:
    """
    Ask the VLM whether a blocking dialog/popup is visible.

    Returns a dict:
        {
            "has_popup": bool,
            "description": str,
            "dismiss_key": str   # e.g. "Enter", "Escape", "Tab+Enter", "none"
        }
    """
    logger.info("Checking for popup / blocking dialog…")
    raw = _call_vlm(_POPUP_PROMPT, screenshot)
    logger.debug("Popup check response: %s", raw)
    result = _parse_json(raw)
    if result.get("has_popup"):
        logger.warning("Popup detected: %s (dismiss: %s)", result.get("description"), result.get("dismiss_key"))
    return result
