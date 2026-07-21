"""Tests for VLM JSON response parsing."""

from __future__ import annotations

import json

import pytest

from src.grounding.screenseeker import _parse_json


def test_parse_raw_json() -> None:
    assert _parse_json('{"x": 10, "y": 20}') == {"x": 10, "y": 20}


def test_parse_markdown_fenced_json() -> None:
    text = '```json\n{"x1": 1, "y1": 2, "x2": 3, "y2": 4}\n```'
    assert _parse_json(text) == {"x1": 1, "y1": 2, "x2": 3, "y2": 4}


def test_parse_markdown_fence_without_language() -> None:
    text = '```\n{"has_popup": false}\n```'
    assert _parse_json(text) == {"has_popup": False}


def test_parse_invalid_json_raises() -> None:
    with pytest.raises(json.JSONDecodeError):
        _parse_json("not json at all")
