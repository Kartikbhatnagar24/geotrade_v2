"""
pipeline/scoring/store.py
──────────────────────────
Persists daily_signals to MongoDB and exports a CSV for notebooks.

Hygiene rules enforced here:
  1. Phantom "WLD" rows from earlier pipeline versions are deleted on every run.
  2. The collection is reconciled to the freshly-computed signal set: any
     (date, iso) pair that no longer appears in the new compute is removed.
     Without this, signals from articles that have aged out of the ingestion
     window keep serving as "current" tension on the globe.
  3. A retention cap drops anything older than DAILY_SIGNAL_RETENTION_DAYS so
     /signals time-series and /events stay tied to the live data window.
"""

from datetime import datetime, timedelta, timezone

import pandas as pd
from tqdm import tqdm

from config.settings import settings
from pipeline.utils.db import get_db


# Keep ~6 months of daily signals; the UI's longest history view is well below this.
DAILY_SIGNAL_RETENTION_DAYS = 180


def ensure_indexes():
    col = get_db()[settings.COL_DAILY_SIGNALS]
    col.create_index([("date", 1), ("iso", 1)], unique=True)
    col.create_index("tension_score")
    col.create_index("tension_label")
    col.create_index("iso")


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


def reconcile_signals(signals: list[dict]) -> dict:
    """
    Remove daily_signals that no longer match the freshly computed set.

    Rules:
      - Always delete iso == "WLD" (phantom 'World' entries from older pipeline runs).
      - Drop rows older than DAILY_SIGNAL_RETENTION_DAYS.
      - Within the retention window, drop (date, iso) pairs that are NOT present
        in the current `signals` list — they are signals whose source events
        have aged out of the ingestion window.

    Returns a dict with deleted counts for logging.
    """
    col = get_db()[settings.COL_DAILY_SIGNALS]

    # 1. Phantom WLD removal — runs unconditionally
    wld_deleted = col.delete_many({"iso": "WLD"}).deleted_count

    # 2. Retention-window prune
    cutoff_date = (datetime.now(timezone.utc) - timedelta(days=DAILY_SIGNAL_RETENTION_DAYS)) \
                    .strftime("%Y-%m-%d")
    old_deleted = col.delete_many({"date": {"$lt": cutoff_date}}).deleted_count

    # 3. Drop (date, iso) pairs no longer produced by the scorer (within window)
    fresh_keys = {(s["date"], s["iso"]) for s in signals}
    fresh_dates = sorted({d for d, _ in fresh_keys})
    if not fresh_dates:
        return {"wld_deleted": wld_deleted, "old_deleted": old_deleted, "stale_pair_deleted": 0}

    stale_deleted = 0
    # Iterate per-date so we don't try to materialise all keys server-side.
    for date in fresh_dates:
        isos_for_date = [iso for d, iso in fresh_keys if d == date]
        result = col.delete_many({
            "date": date,
            "iso":  {"$nin": isos_for_date},
        })
        stale_deleted += result.deleted_count

    return {
        "wld_deleted":         wld_deleted,
        "old_deleted":         old_deleted,
        "stale_pair_deleted":  stale_deleted,
    }


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
