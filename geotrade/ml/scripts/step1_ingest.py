"""
scripts/step1_ingest.py — News Ingestion
=========================================
Fetches geopolitical news from NewsAPI / GDELT / RSS / Guardian / sample data
and stores deduplicated articles in MongoDB: raw_articles

Sources (in order of richness):
  1. NewsAPI      — requires NEWS_API_KEY   (most articles, paginated)
  2. GDELT        — free, no key, 90-day    (broadest coverage)
  3. RSS feeds    — 16 international feeds  (near real-time)
  4. Guardian     — requires GUARDIAN_API_KEY (high quality, full body text)
  5. Sample data  — bundled offline fallback

Run (from project root):
    python scripts/step1_ingest.py
"""

import sys
from pathlib import Path
_ML = Path(__file__).resolve().parent.parent        # geotrade/ml
_ROOT = _ML.parent                                   # geotrade
sys.path.insert(0, str(_ROOT))   # for config.*
sys.path.insert(0, str(_ML))     # for pipeline.*

from datetime import datetime, timedelta, timezone

from config.settings import settings
from pipeline.utils.logger import StepLogger
from pipeline.ingestion.sources import (
    fetch_newsapi, fetch_gdelt, fetch_rss_feeds,
    fetch_guardian, fetch_sample_data,
)
from pipeline.ingestion.store import deduplicate, insert_articles, count_total

log = StepLogger("Step 1 — News Ingestion")


def main():
    log.header()

    from_date = (datetime.now(timezone.utc) - timedelta(days=settings.INGESTION_DAYS_BACK)
                 ).strftime("%Y-%m-%d")
    all_articles: list[dict] = []

    # ── Source 1: NewsAPI ──────────────────────────────────────
    log.section("NewsAPI")
    if settings.NEWS_API_KEY:
        arts = fetch_newsapi(from_date)
        all_articles.extend(arts)
        log.success(f"{len(arts)} articles fetched")
    else:
        log.warn("NEWS_API_KEY not set — skipping (add it to .env for more data)")

    # ── Source 2: GDELT ──────────────────────────────────────────
    log.section("GDELT (free, 90-day, no key)")
    gdelt_from = (datetime.now(timezone.utc) - timedelta(days=90)).strftime("%Y-%m-%d")
    arts = fetch_gdelt(gdelt_from)
    all_articles.extend(arts)
    log.success(f"{len(arts)} articles from GDELT")

    # ── Source 3: RSS feeds (16 international sources) ─────────
    log.section("RSS Feeds (16 sources)")
    arts = fetch_rss_feeds()
    all_articles.extend(arts)
    log.success(f"{len(arts)} articles from RSS feeds")

    # ── Source 4: Guardian API ─────────────────────────────────
    log.section("Guardian API")
    guardian_key = getattr(settings, "GUARDIAN_API_KEY", "")
    if guardian_key:
        arts = fetch_guardian(from_date)
        all_articles.extend(arts)
        log.success(f"{len(arts)} articles from Guardian (with full body text)")
    else:
        log.warn("GUARDIAN_API_KEY not set — skipping (free key at open-platform.theguardian.com)")

    # ── Source 5: Sample data ──────────────────────────────────
    log.section("Sample Dataset")
    arts = fetch_sample_data()
    all_articles.extend(arts)
    log.success(f"{len(arts)} bundled sample articles loaded")

    # ── Dedup + cap ────────────────────────────────────────────
    unique = deduplicate(all_articles)[: settings.MAX_ARTICLES]
    log.info(f"After dedup + cap: {len(unique)} articles")

    # ── Insert to MongoDB ──────────────────────────────────────
    log.section("MongoDB Insert")
    inserted, skipped = insert_articles(unique)

    log.footer({
        "Total fetched":     len(all_articles),
        "Unique / inserted": f"{len(unique)} / {inserted}",
        "Duplicates skipped": skipped,
        "Total in collection": count_total(),
        "Next step":         "python scripts/step2_nlp.py",
    })


if __name__ == "__main__":
    main()
