"""
pipeline/ingestion/store.py
────────────────────────────
Handles deduplication and insertion of raw articles into MongoDB.
"""

from tqdm import tqdm
from config.settings import settings
from pipeline.utils.db import get_db


def ensure_indexes():
    """Create indexes on raw_articles if they don't exist."""
    col = get_db()[settings.COL_RAW_ARTICLES]
    col.create_index("hash", unique=True)
    col.create_index("published_at")
    col.create_index("processed")


def deduplicate(articles: list[dict]) -> list[dict]:
    """Remove in-memory duplicates by hash before hitting MongoDB."""
    seen = set()
    unique = []
    for art in articles:
        h = art.get("hash", "")
        if h and h not in seen and art.get("title") and art.get("url"):
            seen.add(h)
            unique.append(art)
    return unique


def insert_articles(articles: list[dict]) -> tuple[int, int]:
    """
    Insert articles into raw_articles collection.
    Returns (inserted, skipped_duplicates).
    """
    ensure_indexes()
    col = get_db()[settings.COL_RAW_ARTICLES]

    inserted = skipped = 0
    for art in tqdm(articles, desc="  Storing articles", unit="doc", leave=False):
        try:
            col.insert_one(art)
            inserted += 1
        except Exception:
            skipped += 1  # duplicate key → already exists

    return inserted, skipped


def count_total() -> int:
    return get_db()[settings.COL_RAW_ARTICLES].count_documents({})
