"""
pipeline/utils/text.py
───────────────────────
Shared text preprocessing utilities used by ingestion and NLP steps.
"""

import hashlib
import re
from bs4 import BeautifulSoup


def clean_html(text: str | None) -> str:
    """Strip HTML tags and normalize whitespace."""
    if not text:
        return ""
    return " ".join(BeautifulSoup(text, "lxml").get_text().split())


def make_hash(url: str, title: str) -> str:
    """SHA-256 deduplication key from url + title."""
    key = f"{url.strip().lower()}|{title.strip().lower()}"
    return hashlib.sha256(key.encode()).hexdigest()


def truncate(text: str, max_chars: int = 512) -> str:
    """Truncate to model input limit without cutting mid-word."""
    if len(text) <= max_chars:
        return text
    return text[:max_chars].rsplit(" ", 1)[0]
