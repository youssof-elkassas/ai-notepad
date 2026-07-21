"""
JSONPlaceholder API client.
Fetches blog posts from POSTS_API_URL (default: JSONPlaceholder /posts).
"""

from __future__ import annotations

import os

import requests
from dotenv import load_dotenv

from src.utils.logger import get_logger

load_dotenv()

logger = get_logger(__name__)

DEFAULT_POSTS_API_URL = "https://jsonplaceholder.typicode.com/posts"
_TIMEOUT = 10  # seconds


def get_posts_api_url() -> str:
    return os.getenv("POSTS_API_URL", DEFAULT_POSTS_API_URL)


def fetch_posts(limit: int = 10) -> list[dict]:
    """
    Fetch the first `limit` posts from POSTS_API_URL.

    Returns a list of dicts with keys: id, title, body, userId.
    Raises requests.HTTPError on non-2xx responses.
    """
    url = get_posts_api_url()
    logger.info("Fetching %d posts from %s", limit, url)

    response = requests.get(url, params={"_limit": limit}, timeout=_TIMEOUT)
    response.raise_for_status()

    posts = response.json()
    logger.info("Fetched %d posts successfully.", len(posts))
    return posts
