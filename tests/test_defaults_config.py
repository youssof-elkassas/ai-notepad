"""Tests for grounding query / visual description config."""

from __future__ import annotations

from src.grounding import defaults


def test_default_grounding_query(monkeypatch) -> None:
    monkeypatch.delenv("GROUNDING_QUERY", raising=False)
    assert defaults.get_grounding_query() == defaults.DEFAULT_GROUNDING_QUERY


def test_custom_grounding_query(monkeypatch) -> None:
    monkeypatch.setenv("GROUNDING_QUERY", "Recycle Bin desktop icon")
    assert defaults.get_grounding_query() == "Recycle Bin desktop icon"


def test_default_visual_description(monkeypatch) -> None:
    monkeypatch.delenv("GROUNDING_VISUAL_DESCRIPTION", raising=False)
    assert defaults.get_visual_description() == defaults.DEFAULT_VISUAL_DESCRIPTION


def test_visual_description_expands_escaped_newlines(monkeypatch) -> None:
    monkeypatch.setenv(
        "GROUNDING_VISUAL_DESCRIPTION",
        "- line one\\n- line two",
    )
    assert defaults.get_visual_description() == "- line one\n- line two"
