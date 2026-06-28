"""
ScreenSeekeR — two-stage cascaded VLM grounding engine.

Inspired by ScreenSpot-Pro / ScreenSeekeR (arXiv:2504.07981):
  Stage 1 (Planner):  Full screenshot → MLLM → coarse bounding box
  Stage 2 (Grounder): Cropped region  → MLLM → precise center (x, y)

Stage 1 uses a quadrant-scan fallback: if the first full-screenshot attempt
fails in Stage 2 (wrong region predicted), subsequent retries divide the
screen into quadrants and check each one individually. This gives the VLM a
960×540 image instead of 1920×1080, making each tiny desktop icon roughly
twice as large and far easier to locate reliably.
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

from src.automation.screen import Region, crop_region, image_to_base64, save_screenshot
from src.utils.logger import get_logger

load_dotenv()

logger = get_logger(__name__)

# ── Config ────────────────────────────────────────────────────────────────────
_PROVIDER = os.getenv("LLM_PROVIDER", "gemini").lower()
_GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")
_OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4o")
_MAX_RETRIES = int(os.getenv("MAX_GROUNDING_RETRIES", "3"))

# ── VLM trace (debug screenshots sent to the model) ───────────────────────────
_VLM_TRACE_DIR = Path("screenshots/vlm_trace")
_trace_counter = 0

# ── Coordinate cache ──────────────────────────────────────────────────────────
_coord_cache: dict[str, tuple[int, int]] = {}

# ── Prompts ───────────────────────────────────────────────────────────────────

_STAGE1_PROMPT = """You are a GUI grounding agent analyzing a Windows desktop screenshot.

Your task: locate the UI element described as: "{query}"

Visual description of the target:
- A small Windows desktop shortcut icon, approximately 32-48 pixels wide.
- The Notepad icon shows a notepad or document with horizontal text lines, \
typically in blue/white colors or a pencil-and-paper illustration.
- It has a short text label directly underneath it reading "Notepad".
- It sits on the desktop surface (NOT inside the taskbar at the very bottom).
- It could be ANYWHERE in the image — do not assume any particular location.

Instructions:
- Scan the ENTIRE image carefully before answering, including corners and edges.
- Look specifically for a small icon-sized element (~30-60 px) with a label underneath.
- This image is {width}×{height} pixels. Coordinates must be within these bounds.
- If you cannot find the element, return all zeros.

Return ONLY valid JSON:
{{"x1": <int>, "y1": <int>, "x2": <int>, "y2": <int>}}

Where x1,y1 is the top-left and x2,y2 is the bottom-right of the bounding box, \
in pixels within THIS image.
If not found: {{"x1": 0, "y1": 0, "x2": 0, "y2": 0}}
Return ONLY the JSON, no explanation."""

_STAGE2_PROMPT = """You are a GUI grounding agent analyzing a cropped screenshot region.

Your task: pinpoint the exact center pixel of: "{query}"

Visual description:
- A small Windows desktop shortcut icon (~32-48 px wide).
- The Notepad icon: a notepad or document with horizontal lines, blue/white or \
pencil-and-paper style, with a text label "Notepad" underneath.
- There may be other icons nearby — pick only the one that best matches.

This image is exactly {width}×{height} pixels.

Return ONLY valid JSON:
{{"x": <int>, "y": <int>}}

Where x (0 to {width_max}) and y (0 to {height_max}) are the center pixel within \
THIS image, not the original screen.

Rules:
- Return your best estimate even if not 100% certain.
- Only return {{"x": -1, "y": -1}} if NO desktop icon is visible anywhere in the image.
- Return ONLY the JSON, no explanation."""

_POPUP_PROMPT = """You are a GUI agent. Analyze this screenshot.

Is there any dialog box, popup, alert, or modal window blocking the main UI?

Return ONLY valid JSON:
{{"has_popup": <bool>, "description": "<what it says>", "dismiss_key": "<Enter|Escape|Tab+Enter|none>"}}

Return ONLY the JSON, no explanation."""


# ── VLM client factory ────────────────────────────────────────────────────────

def _save_vlm_trace(img: Image.Image, label: str) -> Path:
    """Persist a copy of every image sent to the VLM for debugging."""
    global _trace_counter
    _trace_counter += 1
    _VLM_TRACE_DIR.mkdir(parents=True, exist_ok=True)
    safe_label = re.sub(r"[^\w\-.]", "_", label)
    path = _VLM_TRACE_DIR / f"{_trace_counter:04d}_{safe_label}.png"
    save_screenshot(img, path)
    logger.info("VLM trace saved → %s", path)
    return path


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


def _call_vlm(prompt: str, img: Image.Image, trace_label: str) -> str:
    """Route to the configured VLM provider, saving a trace image first."""
    _save_vlm_trace(img, trace_label)
    if _PROVIDER == "openai":
        return _call_openai(prompt, img)
    return _call_gemini(prompt, img)


# ── JSON parsing ──────────────────────────────────────────────────────────────

def _parse_json(text: str) -> dict:
    """Extract and parse JSON from VLM response, handling markdown fences."""
    text = text.strip()
    text = re.sub(r"^```(?:json)?\s*", "", text)
    text = re.sub(r"\s*```$", "", text)
    return json.loads(text)


def _normalize_bbox_if_needed(
    x1: int, y1: int, x2: int, y2: int, img_w: int, img_h: int,
) -> tuple[int, int, int, int]:
    """
    Convert Gemini 0-1000 normalized bbox to pixel coordinates when detected.

    On full-screen images (>=1000px), Gemini often returns bbox values in 0-1000
    scale even when the prompt asks for pixels. Quadrant crops (<1000px wide) are
    left as-is since their coords are already in local pixels.
    """
    if x2 > img_w or y2 > img_h:
        logger.debug(
            "[Stage 1] Normalizing out-of-bounds bbox (%d,%d,%d,%d) from 0-1000 scale.",
            x1, y1, x2, y2,
        )
        return (
            int(x1 / 1000 * img_w),
            int(y1 / 1000 * img_h),
            int(x2 / 1000 * img_w),
            int(y2 / 1000 * img_h),
        )

    if img_w >= 1000 and img_h >= 1000 and max(x1, y1, x2, y2) <= 1000:
        logger.debug(
            "[Stage 1] Normalizing bbox (%d,%d,%d,%d) from 0-1000 scale to %dx%d px.",
            x1, y1, x2, y2, img_w, img_h,
        )
        return (
            int(x1 / 1000 * img_w),
            int(y1 / 1000 * img_h),
            int(x2 / 1000 * img_w),
            int(y2 / 1000 * img_h),
        )

    return x1, y1, x2, y2


# ── Stage 1: coarse localization ──────────────────────────────────────────────

def _query_region_for_bbox(
    img: Image.Image,
    query: str,
    trace_label: str,
    offset_x: int = 0,
    offset_y: int = 0,
) -> Optional[Region]:
    """
    Ask the VLM for a bounding box within `img`.
    If found, maps the result back to full-screen coordinates using offset_x/offset_y.
    Returns a Region or None.
    """
    prompt = _STAGE1_PROMPT.format(query=query, width=img.width, height=img.height)
    raw = _call_vlm(prompt, img, trace_label)
    logger.debug("[Stage 1] Raw response: %s", raw)

    data = _parse_json(raw)
    x1, y1, x2, y2 = data["x1"], data["y1"], data["x2"], data["y2"]

    if x1 == 0 and y1 == 0 and x2 == 0 and y2 == 0:
        return None

    x1, y1, x2, y2 = _normalize_bbox_if_needed(x1, y1, x2, y2, img.width, img.height)

    return Region(
        x1=max(0, offset_x + x1),
        y1=max(0, offset_y + y1),
        x2=min(offset_x + img.width, offset_x + x2),
        y2=min(offset_y + img.height, offset_y + y2),
    )


def _stage1_full(screenshot: Image.Image, query: str, attempt: int) -> Optional[Region]:
    """Stage 1 on the complete screenshot."""
    logger.info("[Stage 1] Sending full %dx%d screenshot to VLM for: %r",
                screenshot.width, screenshot.height, query)
    trace_label = f"stage1_attempt{attempt}_full_{screenshot.width}x{screenshot.height}"
    region = _query_region_for_bbox(screenshot, query, trace_label)
    if region:
        logger.info("[Stage 1] Coarse region: %s", region)
    else:
        logger.warning("[Stage 1] Element not found in full screenshot.")
    return region


def _stage1_quadrant_scan(screenshot: Image.Image, query: str, attempt: int) -> Optional[Region]:
    """
    Divide the screen into 4 quadrants and scan each one individually.

    Each quadrant is 960×540 — the target icon is effectively 2× larger relative
    to the image, giving the VLM a much better chance of identifying it correctly.
    Stops and returns as soon as any quadrant yields a positive result.
    """
    w, h = screenshot.width, screenshot.height
    hw, hh = w // 2, h // 2

    quadrants = [
        (0,  0,  hw, hh, "top-left"),
        (hw, 0,  w,  hh, "top-right"),
        (0,  hh, hw, h,  "bottom-left"),
        (hw, hh, w,  h,  "bottom-right"),
    ]

    for (qx1, qy1, qx2, qy2, name) in quadrants:
        quad_img = screenshot.crop((qx1, qy1, qx2, qy2))
        logger.info("[Stage 1 Scan] Checking %s quadrant (%dx%d) for: %r",
                    name, quad_img.width, quad_img.height, query)

        trace_label = (
            f"stage1_attempt{attempt}_quadrant_{name}_{quad_img.width}x{quad_img.height}"
        )
        region = _query_region_for_bbox(
            quad_img, query, trace_label, offset_x=qx1, offset_y=qy1,
        )
        if region is not None:
            logger.info("[Stage 1 Scan] Found in %s quadrant: %s", name, region)
            return region

        logger.debug("[Stage 1 Scan] Not found in %s quadrant.", name)

    logger.warning("[Stage 1 Scan] Element not found in any quadrant.")
    return None


# ── Stage 2: fine localization ────────────────────────────────────────────────

def _stage2_fine(
    screenshot: Image.Image,
    region: Region,
    query: str,
    attempt: int,
) -> Optional[tuple[int, int]]:
    """
    Stage 2 — Grounder: crop to the Stage 1 region and pinpoint the exact center.
    Returns (screen_x, screen_y) or None if not found (caller should retry with
    a different Stage 1 strategy).
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

    trace_label = f"stage2_attempt{attempt}_crop_{crop.width}x{crop.height}"
    raw = _call_vlm(prompt, crop, trace_label)
    logger.debug("[Stage 2] Raw response: %s", raw)

    data = _parse_json(raw)
    lx, ly = data["x"], data["y"]

    if lx == -1 and ly == -1:
        logger.warning("[Stage 2] VLM reported element not found in crop.")
        return None

    # Gemini sometimes returns coordinates on a 0-1000 normalized scale.
    # Detect and rescale if the value exceeds the crop dimension.
    if lx > crop.width or ly > crop.height:
        logger.debug(
            "[Stage 2] Normalizing out-of-bounds (%d,%d) from 0-1000 scale to %dx%d px.",
            lx, ly, crop.width, crop.height,
        )
        lx = int(lx / 1000 * crop.width)
        ly = int(ly / 1000 * crop.height)

    sx, sy = padded.map_local_to_screen(lx, ly)
    logger.info("[Stage 2] Fine center: local=(%d,%d) → screen=(%d,%d)", lx, ly, sx, sy)
    return sx, sy


# ── Coordinate cache helpers ──────────────────────────────────────────────────

def get_cached_coords(query: str) -> Optional[tuple[int, int]]:
    """Return cached screen coordinates for a query, or None if not cached."""
    return _coord_cache.get(query)


def set_cached_coords(query: str, x: int, y: int) -> None:
    """Store screen coordinates for a query."""
    _coord_cache[query] = (x, y)
    logger.debug("Cached coords for %r: (%d, %d)", query, x, y)


def invalidate_cache(query: Optional[str] = None) -> None:
    """Clear one cache entry or the entire cache (useful for testing)."""
    if query is None:
        _coord_cache.clear()
        logger.debug("Coordinate cache cleared (all entries).")
    else:
        _coord_cache.pop(query, None)
        logger.debug("Coordinate cache cleared for %r.", query)


# ── Public API ────────────────────────────────────────────────────────────────

def ground(
    query: str,
    screenshot: Image.Image,
    save_annotated_to: Optional[Path] = None,
) -> tuple[int, int]:
    """
    Locate a UI element on screen using two-stage cascaded VLM grounding.

    Retry strategy:
      Attempt 1 — Stage 1 on full screenshot → Stage 2 on crop
      Attempt 2 — Stage 1 quadrant scan      → Stage 2 on crop
      Attempt 3 — Stage 1 quadrant scan      → Stage 2 on crop
                  (last resort: Stage 1 box center if Stage 2 returns None)

    Args:
        query:              Plain-English description of the target element.
        screenshot:         Full-screen PIL Image.
        save_annotated_to:  If provided, save an annotated screenshot to this Path.

    Returns:
        (x, y) screen coordinates of the element center.

    Raises:
        RuntimeError: if grounding fails after all retries.
    """
    from src.grounding.annotator import save_annotated

    last_exc: Optional[Exception] = None
    last_region: Optional[Region] = None

    for attempt in range(1, _MAX_RETRIES + 1):
        logger.info("Grounding attempt %d/%d for: %r", attempt, _MAX_RETRIES, query)
        try:
            # Stage 1: full screenshot on first attempt, quadrant scan on retries.
            if attempt == 1:
                region = _stage1_full(screenshot, query, attempt)
            else:
                region = _stage1_quadrant_scan(screenshot, query, attempt)

            if region is None:
                raise RuntimeError("Stage 1 returned no region.")

            last_region = region

            # Stage 2: zoom into the Stage 1 region for precise center.
            center = _stage2_fine(screenshot, region, query, attempt)

            # Last attempt: if Stage 2 still fails, fall back to Stage 1 box center.
            if center is None and attempt == _MAX_RETRIES:
                sx = (region.x1 + region.x2) // 2
                sy = (region.y1 + region.y2) // 2
                logger.warning(
                    "[Stage 2] Last attempt — using Stage 1 box center: screen=(%d,%d)", sx, sy
                )
                center = (sx, sy)

            if center is None:
                raise RuntimeError("Stage 2 returned no center.")

            sx, sy = center

            # Sanity-check: coordinates must be within screen bounds.
            if not (0 <= sx < screenshot.width and 0 <= sy < screenshot.height):
                raise ValueError(
                    f"Grounded coordinates ({sx},{sy}) out of screen bounds "
                    f"({screenshot.width}x{screenshot.height})."
                )

            logger.info("Grounding SUCCESS: %r → screen=(%d,%d)", query, sx, sy)

            if save_annotated_to is not None:
                save_annotated(
                    img=screenshot,
                    region=last_region,
                    center=(sx, sy),
                    label=query,
                    path=save_annotated_to,
                    stage="ScreenSeekeR",
                )

            return sx, sy

        except Exception as exc:
            last_exc = exc
            delay = 2 ** attempt
            logger.warning(
                "Grounding attempt %d failed: %s. Retrying in %.1fs…",
                attempt, exc, delay,
            )
            time.sleep(delay)

    raise RuntimeError(
        f"Grounding failed for {query!r} after {_MAX_RETRIES} attempts. "
        f"Last error: {last_exc}"
    )


def ground_and_cache(
    query: str,
    screenshot: Image.Image,
    save_annotated_to: Optional[Path] = None,
) -> tuple[int, int]:
    """Run full VLM grounding and store the result in the coordinate cache."""
    x, y = ground(query, screenshot, save_annotated_to=save_annotated_to)
    set_cached_coords(query, x, y)
    return x, y


def detect_popup(screenshot: Image.Image) -> dict:
    """
    Ask the VLM whether a blocking dialog/popup is visible.

    Returns a dict with keys: has_popup (bool), description (str), dismiss_key (str).
    """
    logger.info("Checking for popup / blocking dialog…")
    trace_label = f"popup_check_{screenshot.width}x{screenshot.height}"
    raw = _call_vlm(_POPUP_PROMPT, screenshot, trace_label)
    logger.debug("Popup check response: %s", raw)
    result = _parse_json(raw)
    if result.get("has_popup"):
        logger.warning(
            "Popup detected: %s (dismiss: %s)",
            result.get("description"), result.get("dismiss_key"),
        )
    return result
