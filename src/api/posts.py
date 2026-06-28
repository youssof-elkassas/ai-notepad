"""
JSONPlaceholder API client.
Fetches blog posts from https://jsonplaceholder.typicode.com/posts.
"""

from __future__ import annotations

import requests

from src.utils.logger import get_logger

logger = get_logger(__name__)

_BASE_URL = "https://jsonplaceholder.typicode.com"
_TIMEOUT = 10  # seconds


def fetch_posts(limit: int = 10) -> list[dict]:
    """
    Fetch the first `limit` posts from JSONPlaceholder.

    Returns a list of dicts with keys: id, title, body, userId.
    Raises requests.HTTPError on non-2xx responses.
    """
    url = f"{_BASE_URL}/posts"
    logger.info("Fetching %d posts from %s", limit, url)

    response = requests.get(url, params={"_limit": limit}, timeout=_TIMEOUT)
    response.raise_for_status()

    posts = response.json()
    logger.info("Fetched %d posts successfully.", len(posts))
    return posts
