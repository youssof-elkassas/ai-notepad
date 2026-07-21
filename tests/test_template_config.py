"""Tests for template-matching path and threshold config."""

from __future__ import annotations

from pathlib import Path

from src.grounding import template_match as tm


def test_default_template_path(monkeypatch) -> None:
    monkeypatch.delenv("TEMPLATE_IMAGE_PATH", raising=False)
    assert tm.get_template_path() == tm.DEFAULT_TEMPLATE_PATH


def test_custom_template_path(monkeypatch) -> None:
    monkeypatch.setenv("TEMPLATE_IMAGE_PATH", "resources/templates/recycle.png")
    assert tm.get_template_path() == Path("resources/templates/recycle.png")


def test_default_template_matching(monkeypatch) -> None:
    monkeypatch.delenv("TEMPLATE_MATCHING", raising=False)
    assert tm.get_template_matching() == tm.DEFAULT_TEMPLATE_MATCHING


def test_custom_template_matching(monkeypatch) -> None:
    monkeypatch.setenv("TEMPLATE_MATCHING", "0.9")
    assert tm.get_template_matching() == 0.9


def test_default_template_crop_size(monkeypatch) -> None:
    monkeypatch.delenv("TEMPLATE_CROP_SIZE", raising=False)
    assert tm.get_template_crop_size() == tm.DEFAULT_TEMPLATE_CROP_SIZE


def test_custom_template_crop_size(monkeypatch) -> None:
    monkeypatch.setenv("TEMPLATE_CROP_SIZE", "120")
    assert tm.get_template_crop_size() == 120
