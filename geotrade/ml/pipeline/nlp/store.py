"""
pipeline/nlp/store.py
──────────────────────
Read unprocessed articles from MongoDB and persist NLP results.
"""

from datetime import datetime, timezone
from config.settings import settings
from pipeline.utils.db import get_db


def ensure_indexes():
    col = get_db()[settings.COL_PROCESSED_EVENTS]
    col.create_index("article_id", unique=True)
    col.create_index("published_at")
    col.create_index("event_label")


def fetch_unprocessed(limit: int = 1000) -> list[dict]:
    """Return articles that haven't been through NLP yet."""
    return list(
        get_db()[settings.COL_RAW_ARTICLES]
        .find({"processed": False})
        .limit(limit)
    )


def save_event(article: dict, event_label: str, event_score: float,
               sentiment_label: str, sentiment_score: float,
               neg_sentiment: float, countries: list[dict],
               intensity: float = 0.0):
    """
    Upsert processed event and mark source article as done.

    New fields vs v1:
      - intensity_score : keyword-based severity weight (0.0–1.0)
      - has_country_match : False when no countries were extracted
        (these events are stored but excluded from scoring)
    """
    db = get_db()
    doc = {
        "article_id":          str(article["_id"]),
        "title":               article.get("title", ""),
        "description":         article.get("description", ""),
        "url":                 article.get("url", ""),
        "source":              article.get("source", ""),
        "published_at":        article.get("published_at", ""),
        "event_label":         event_label,
        "event_score":         event_score,
        "sentiment_label":     sentiment_label,
        "sentiment_score":     sentiment_score,
        "neg_sentiment_score": neg_sentiment,
        "intensity_score":     intensity,
        "countries":           countries,
        "has_country_match":   len(countries) > 0,
        "processed_at":        datetime.now(timezone.utc).isoformat(),
    }
    db[settings.COL_PROCESSED_EVENTS].update_one(
        {"article_id": str(article["_id"])},
        {"$set": doc},
        upsert=True,
    )
    db[settings.COL_RAW_ARTICLES].update_one(
        {"_id": article["_id"]},
        {"$set": {"processed": True}},
    )


def label_distribution() -> dict[str, int]:
    pipeline = [{"$group": {"_id": "$event_label", "n": {"$sum": 1}}}]
    return {r["_id"]: r["n"] for r in get_db()[settings.COL_PROCESSED_EVENTS].aggregate(pipeline)}


def prune_orphan_events() -> int:
    """
    Delete processed_events whose source raw_article no longer exists.

    Step 1 prunes raw_articles by published_at; this keeps processed_events
    aligned with the live ingestion window so the UI's "recent news" never
    surfaces an event whose origin article has been retired.
    """
    db = get_db()
    raw_ids = {str(_id) for _id in db[settings.COL_RAW_ARTICLES].distinct("_id")}
    if not raw_ids:
        return 0
    return db[settings.COL_PROCESSED_EVENTS].delete_many(
        {"article_id": {"$nin": list(raw_ids)}}
    ).deleted_count
