"""
scripts/maintain_db.py — DB hygiene
====================================
Sweeps the geotrade Mongo collections so the UI/predictor never serve old or
phantom records. Idempotent. Safe to run before or after the normal pipeline,
and intended to run automatically as the last step of run_all.py.

What it does:
  raw_articles      — drop docs older than 2× INGESTION_DAYS_BACK
  processed_events  — drop docs whose source raw_article no longer exists
  daily_signals     — drop iso == "WLD"; drop docs older than 180 days
  ml_predictions    — drop docs whose computed_at is older than 3 days
  tension_forecasts — drop docs older than 7 days (cache reaper)
  llm_briefings     — drop docs older than 7 days (cache reaper)

Also asserts the indexes every collection should have, so existing deployments
catch up the first time the script runs.

Run from the geotrade root:
    python ml/scripts/maintain_db.py
"""

from __future__ import annotations

import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

_ML   = Path(__file__).resolve().parent.parent
_ROOT = _ML.parent
sys.path.insert(0, str(_ROOT))
sys.path.insert(0, str(_ML))

from config.settings import settings
from pipeline.utils.db import get_db
from pipeline.utils.logger import StepLogger

DAILY_SIGNAL_RETENTION_DAYS  = 180
ML_PREDICTION_MAX_AGE_DAYS   = 3
CACHE_MAX_AGE_DAYS           = 7

log = StepLogger("DB Maintenance")


def _ensure_indexes(db) -> None:
    db[settings.COL_RAW_ARTICLES].create_index("hash", unique=True)
    db[settings.COL_RAW_ARTICLES].create_index("published_at")
    db[settings.COL_RAW_ARTICLES].create_index("processed")

    db[settings.COL_PROCESSED_EVENTS].create_index("article_id", unique=True)
    db[settings.COL_PROCESSED_EVENTS].create_index("published_at")
    db[settings.COL_PROCESSED_EVENTS].create_index("event_label")
    db[settings.COL_PROCESSED_EVENTS].create_index("countries.iso")

    db[settings.COL_DAILY_SIGNALS].create_index([("date", 1), ("iso", 1)], unique=True)
    db[settings.COL_DAILY_SIGNALS].create_index("iso")
    db[settings.COL_DAILY_SIGNALS].create_index("tension_score")
    db[settings.COL_DAILY_SIGNALS].create_index("tension_label")

    db["ml_predictions"].create_index("iso2", unique=True)
    db["ml_predictions"].create_index("computed_at")

    db[settings.COL_TENSION_FORECASTS].create_index("iso", unique=True)
    db[settings.COL_TENSION_FORECASTS].create_index("computed_at")
    db[settings.COL_LLM_BRIEFINGS].create_index("iso", unique=True)
    db[settings.COL_LLM_BRIEFINGS].create_index("created_at")


def _prune_raw_articles(db) -> int:
    cutoff = (datetime.now(timezone.utc)
              - timedelta(days=settings.INGESTION_DAYS_BACK * 2)).isoformat()
    return db[settings.COL_RAW_ARTICLES].delete_many(
        {"published_at": {"$lt": cutoff}}
    ).deleted_count


def _prune_orphan_events(db) -> int:
    raw_ids = {str(_id) for _id in db[settings.COL_RAW_ARTICLES].distinct("_id")}
    if not raw_ids:
        return 0
    return db[settings.COL_PROCESSED_EVENTS].delete_many(
        {"article_id": {"$nin": list(raw_ids)}}
    ).deleted_count


def _prune_daily_signals(db) -> tuple[int, int]:
    wld = db[settings.COL_DAILY_SIGNALS].delete_many({"iso": "WLD"}).deleted_count
    cutoff_date = (datetime.now(timezone.utc)
                   - timedelta(days=DAILY_SIGNAL_RETENTION_DAYS)).strftime("%Y-%m-%d")
    old = db[settings.COL_DAILY_SIGNALS].delete_many(
        {"date": {"$lt": cutoff_date}}
    ).deleted_count
    return wld, old


def _prune_predictions(db) -> int:
    cutoff = (datetime.now(timezone.utc)
              - timedelta(days=ML_PREDICTION_MAX_AGE_DAYS)).isoformat()
    return db["ml_predictions"].delete_many(
        {"computed_at": {"$lt": cutoff}}
    ).deleted_count


def _prune_cache(db, collection: str, ts_field: str) -> int:
    cutoff = (datetime.now(timezone.utc)
              - timedelta(days=CACHE_MAX_AGE_DAYS)).isoformat()
    return db[collection].delete_many({ts_field: {"$lt": cutoff}}).deleted_count


def main() -> int:
    log.header()
    db = get_db()

    log.section("Indexes")
    _ensure_indexes(db)
    log.success("indexes verified on all collections")

    log.section("raw_articles")
    n = _prune_raw_articles(db)
    log.success(f"{n} pruned (>{settings.INGESTION_DAYS_BACK*2}d)")

    log.section("processed_events")
    n = _prune_orphan_events(db)
    log.success(f"{n} orphans pruned")

    log.section("daily_signals")
    wld, old = _prune_daily_signals(db)
    log.success(f"{wld} WLD removed, {old} >{DAILY_SIGNAL_RETENTION_DAYS}d removed")

    log.section("ml_predictions")
    n = _prune_predictions(db)
    log.success(f"{n} predictions older than {ML_PREDICTION_MAX_AGE_DAYS}d removed")

    log.section("tension_forecasts")
    n = _prune_cache(db, settings.COL_TENSION_FORECASTS, "computed_at")
    log.success(f"{n} stale forecasts removed")

    log.section("llm_briefings")
    n = _prune_cache(db, settings.COL_LLM_BRIEFINGS, "created_at")
    log.success(f"{n} stale briefings removed")

    log.footer({
        "raw_articles":     db[settings.COL_RAW_ARTICLES].count_documents({}),
        "processed_events": db[settings.COL_PROCESSED_EVENTS].count_documents({}),
        "daily_signals":    db[settings.COL_DAILY_SIGNALS].count_documents({}),
        "ml_predictions":   db["ml_predictions"].count_documents({}),
        "tension_forecasts": db[settings.COL_TENSION_FORECASTS].count_documents({}),
        "llm_briefings":    db[settings.COL_LLM_BRIEFINGS].count_documents({}),
    })
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
