"""Shared fixtures for unit tests."""

from __future__ import annotations

import pytest
from PIL import Image


@pytest.fixture
def blank_screenshot() -> Image.Image:
    """Small blank RGB image used as a stand-in full-screen capture."""
    return Image.new("RGB", (1920, 1080), color=(30, 30, 30))
