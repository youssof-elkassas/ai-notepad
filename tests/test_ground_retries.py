"""Mocked ScreenSeekeR ground() retry and fallback selection tests."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from PIL import Image

import src.grounding.screenseeker as ss
from src.automation.screen import Region


@pytest.fixture(autouse=True)
def _fast_retries(monkeypatch) -> None:
    """Skip exponential backoff sleeps between grounding attempts."""
    monkeypatch.setattr(ss.time, "sleep", lambda *_a, **_k: None)


@pytest.fixture
def screenshot() -> Image.Image:
    return Image.new("RGB", (1920, 1080), color=(40, 40, 40))


def test_ground_succeeds_on_first_attempt(monkeypatch, screenshot: Image.Image) -> None:
    region = Region(1800, 900, 1880, 980)
    monkeypatch.setattr(ss, "_stage1_full", MagicMock(return_value=region))
    monkeypatch.setattr(ss, "_stage1_quadrant_scan", MagicMock())
    monkeypatch.setattr(ss, "_stage2_fine", MagicMock(return_value=(1840, 940)))
    template = MagicMock()
    monkeypatch.setattr(ss, "try_template_fallback", template)
    monkeypatch.setattr(ss, "is_template_fallback_enabled", MagicMock(return_value=True))

    x, y = ss.ground("Notepad icon", screenshot, visual_description="hint")

    assert (x, y) == (1840, 940)
    ss._stage1_full.assert_called_once()
    ss._stage1_quadrant_scan.assert_not_called()
    template.assert_not_called()


def test_ground_retries_with_quadrant_scan(monkeypatch, screenshot: Image.Image) -> None:
    monkeypatch.setattr(ss, "_MAX_RETRIES", 2)
    region = Region(100, 100, 200, 200)
    monkeypatch.setattr(
        ss,
        "_stage1_full",
        MagicMock(side_effect=RuntimeError("Stage 1 returned no region.")),
    )
    monkeypatch.setattr(ss, "_stage1_quadrant_scan", MagicMock(return_value=region))
    monkeypatch.setattr(ss, "_stage2_fine", MagicMock(return_value=(150, 150)))
    template = MagicMock()
    monkeypatch.setattr(ss, "try_template_fallback", template)

    x, y = ss.ground("Notepad icon", screenshot, visual_description="hint")

    assert (x, y) == (150, 150)
    ss._stage1_full.assert_called_once()
    ss._stage1_quadrant_scan.assert_called_once()
    template.assert_not_called()


def test_ground_last_attempt_uses_stage1_box_center(
    monkeypatch, screenshot: Image.Image,
) -> None:
    monkeypatch.setattr(ss, "_MAX_RETRIES", 1)
    region = Region(10, 20, 30, 40)  # center = (20, 30)
    monkeypatch.setattr(ss, "_stage1_full", MagicMock(return_value=region))
    monkeypatch.setattr(ss, "_stage2_fine", MagicMock(return_value=None))
    template = MagicMock()
    monkeypatch.setattr(ss, "try_template_fallback", template)

    x, y = ss.ground("Notepad icon", screenshot, visual_description="hint")

    assert (x, y) == (20, 30)
    template.assert_not_called()


def test_ground_falls_back_to_template_when_vlm_exhausted(
    monkeypatch, screenshot: Image.Image,
) -> None:
    monkeypatch.setattr(ss, "_MAX_RETRIES", 1)
    monkeypatch.setattr(ss, "_stage1_full", MagicMock(return_value=None))
    monkeypatch.setattr(ss, "is_template_fallback_enabled", MagicMock(return_value=True))
    monkeypatch.setattr(
        ss, "try_template_fallback", MagicMock(return_value=(1850, 920)),
    )

    x, y = ss.ground("Notepad icon", screenshot, visual_description="hint")

    assert (x, y) == (1850, 920)
    ss.try_template_fallback.assert_called_once()


def test_ground_raises_when_vlm_and_template_fail(
    monkeypatch, screenshot: Image.Image,
) -> None:
    monkeypatch.setattr(ss, "_MAX_RETRIES", 1)
    monkeypatch.setattr(ss, "_stage1_full", MagicMock(return_value=None))
    monkeypatch.setattr(ss, "is_template_fallback_enabled", MagicMock(return_value=True))
    monkeypatch.setattr(ss, "try_template_fallback", MagicMock(return_value=None))

    with pytest.raises(RuntimeError, match="Grounding failed"):
        ss.ground("Notepad icon", screenshot, visual_description="hint")


def test_ground_raises_when_template_fallback_disabled(
    monkeypatch, screenshot: Image.Image,
) -> None:
    monkeypatch.setattr(ss, "_MAX_RETRIES", 1)
    monkeypatch.setattr(ss, "_stage1_full", MagicMock(return_value=None))
    monkeypatch.setattr(ss, "is_template_fallback_enabled", MagicMock(return_value=False))
    template = MagicMock()
    monkeypatch.setattr(ss, "try_template_fallback", template)

    with pytest.raises(RuntimeError, match="Grounding failed"):
        ss.ground("Notepad icon", screenshot, visual_description="hint")

    template.assert_not_called()
