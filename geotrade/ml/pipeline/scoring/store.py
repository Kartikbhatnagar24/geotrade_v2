"""
pipeline/scoring/store.py
──────────────────────────
Persists daily_signals to MongoDB and exports a CSV for notebooks.
"""

import pandas as pd
from tqdm import tqdm

from config.settings import settings
from pipeline.utils.db import get_db


def ensure_indexes():
    col = get_db()[settings.COL_DAILY_SIGNALS]
    col.create_index([("date", 1), ("iso", 1)], unique=True)
    col.create_index("tension_score")
    col.create_index("tension_label")


def upsert_signals(signals: list[dict]) -> int:
    """Upsert signals by (date, iso). Returns count upserted."""
    ensure_indexes()
    col = get_db()[settings.COL_DAILY_SIGNALS]
    count = 0
    for sig in tqdm(signals, desc="  Saving signals", unit="sig", leave=False):
        col.update_one(
            {"date": sig["date"], "iso": sig["iso"]},
            {"$set": sig},
            upsert=True,
        )
        count += 1
    return count


def export_csv(signals: list[dict]) -> str:
    """Write signals to data/processed/daily_signals.csv. Returns path."""
    path = settings.DATA_PROCESSED / "daily_signals.csv"
    path.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(signals).to_csv(path, index=False)
    return str(path)


def tension_stats(signals: list[dict]) -> dict:
    if not signals:
        return {}
    scores = [s["tension_score"] for s in signals]
    labels = [s["tension_label"] for s in signals]
    return {
        "total":  len(signals),
        "min":    round(min(scores), 4),
        "max":    round(max(scores), 4),
        "mean":   round(sum(scores) / len(scores), 4),
        "high":   labels.count("high"),
        "medium": labels.count("medium"),
        "low":    labels.count("low"),
    }
