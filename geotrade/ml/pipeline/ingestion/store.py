"""
pipeline/ingestion/store.py
────────────────────────────
Handles deduplication, insertion, and retention pruning of raw articles.

Retention rule:
  raw_articles older than 2× INGESTION_DAYS_BACK are pruned on every ingest.
  The 2× factor gives a comfortable buffer for re-processing without keeping
  unbounded history that would slow NLP and skew "recent news" queries.
"""

from datetime import datetime, timedelta, timezone

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


def prune_old_articles() -> int:
    """
    Delete raw_articles whose published_at is older than 2× INGESTION_DAYS_BACK.

    Returns the number of articles deleted. Anything with no parseable date is
    left alone — it will be filtered out at scoring time anyway.
    """
    cutoff = datetime.now(timezone.utc) - timedelta(days=settings.INGESTION_DAYS_BACK * 2)
    cutoff_iso = cutoff.isoformat()
    col = get_db()[settings.COL_RAW_ARTICLES]
    return col.delete_many({"published_at": {"$lt": cutoff_iso}}).deleted_count


def count_total() -> int:
    return get_db()[settings.COL_RAW_ARTICLES].count_documents({})
