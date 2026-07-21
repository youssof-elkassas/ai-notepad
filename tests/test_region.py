"""Tests for Region geometry helpers."""

from __future__ import annotations

from src.automation.screen import Region


def test_width_height() -> None:
    r = Region(10, 20, 110, 80)
    assert r.width == 100
    assert r.height == 60


def test_map_local_to_screen() -> None:
    r = Region(100, 200, 400, 500)
    assert r.map_local_to_screen(5, 7) == (105, 207)


def test_padded_expands_and_clamps_to_screen() -> None:
    r = Region(900, 400, 940, 440)
    padded = r.padded(pct=0.20, min_size=300, screen_w=1920, screen_h=1080)
    assert padded.width >= 300
    assert padded.height >= 300
    assert padded.x1 >= 0
    assert padded.y1 >= 0
    assert padded.x2 <= 1920
    assert padded.y2 <= 1080
    assert padded.x1 < r.x1
    assert padded.y1 < r.y1


def test_padded_near_bottom_right_clamps() -> None:
    r = Region(1850, 1000, 1900, 1050)
    padded = r.padded(pct=0.20, min_size=300, screen_w=1920, screen_h=1080)
    assert padded.x2 == 1920
    assert padded.y2 == 1080
    assert padded.x1 >= 0
    assert padded.y1 >= 0
