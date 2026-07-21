"""Tests for Gemini bbox coordinate normalization."""

from __future__ import annotations

from src.grounding.screenseeker import _normalize_bbox_if_needed


def test_passthrough_when_already_pixel_coords() -> None:
    # max coord > 1000 → clearly pixel space on a 1920x1080 screen
    assert _normalize_bbox_if_needed(1200, 800, 1400, 950, 1920, 1080) == (
        1200, 800, 1400, 950,
    )


def test_normalize_0_1000_scale_on_fullscreen() -> None:
    # max coord <= 1000 and image >= 1000 → treat as 0-1000 scale
    result = _normalize_bbox_if_needed(500, 250, 750, 500, 1920, 1080)
    assert result == (
        int(500 / 1000 * 1920),
        int(250 / 1000 * 1080),
        int(750 / 1000 * 1920),
        int(500 / 1000 * 1080),
    )


def test_normalize_out_of_bounds_as_0_1000_scale() -> None:
    result = _normalize_bbox_if_needed(100, 100, 1500, 1200, 1920, 1080)
    assert result == (
        int(100 / 1000 * 1920),
        int(100 / 1000 * 1080),
        int(1500 / 1000 * 1920),
        int(1200 / 1000 * 1080),
    )


def test_small_crop_keeps_local_pixels() -> None:
    # Quadrant-sized image: coords already local pixels, leave as-is
    assert _normalize_bbox_if_needed(100, 50, 200, 150, 960, 540) == (
        100, 50, 200, 150,
    )
