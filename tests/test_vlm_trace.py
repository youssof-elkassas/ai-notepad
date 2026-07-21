"""Tests for VLM trace screenshot path building."""

from __future__ import annotations

from pathlib import Path

from PIL import Image

import src.grounding.screenseeker as ss


def test_save_vlm_trace_writes_numbered_file(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(ss, "_VLM_TRACE_ENABLED", True)
    monkeypatch.setattr(ss, "_VLM_TRACE_DIR", tmp_path)
    monkeypatch.setattr(ss, "_trace_counter", 0)

    img = Image.new("RGB", (10, 10), color=(0, 0, 0))
    path = ss._save_vlm_trace(img, "stage1_attempt1_full_1920x1080")

    assert path is not None
    assert path.parent == tmp_path
    assert path.name == "0001_stage1_attempt1_full_1920x1080.png"
    assert path.exists()


def test_save_vlm_trace_sanitizes_label(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(ss, "_VLM_TRACE_ENABLED", True)
    monkeypatch.setattr(ss, "_VLM_TRACE_DIR", tmp_path)
    monkeypatch.setattr(ss, "_trace_counter", 0)

    img = Image.new("RGB", (4, 4), color=(1, 1, 1))
    path = ss._save_vlm_trace(img, "stage1 quadrant top-left!")

    assert path is not None
    assert path.name == "0001_stage1_quadrant_top-left_.png"


def test_save_vlm_trace_disabled_returns_none(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(ss, "_VLM_TRACE_ENABLED", False)
    monkeypatch.setattr(ss, "_VLM_TRACE_DIR", tmp_path)

    img = Image.new("RGB", (4, 4), color=(0, 0, 0))
    assert ss._save_vlm_trace(img, "ignored") is None
    assert list(tmp_path.iterdir()) == []
