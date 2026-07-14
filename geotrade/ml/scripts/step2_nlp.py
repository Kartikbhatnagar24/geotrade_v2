"""
scripts/step2_nlp.py - NLP Processing
=======================================
Reads unprocessed articles from raw_articles.
Runs: event classification + sentiment analysis + country NER.
Writes results to MongoDB: processed_events

Run (from project root):
    python scripts/step2_nlp.py              # process new articles only
    python scripts/step2_nlp.py --reprocess  # re-run NLP on all articles
"""

import argparse
import sys
from pathlib import Path
_ML = Path(__file__).resolve().parent.parent        # geotrade/ml
_ROOT = _ML.parent                                   # geotrade
sys.path.insert(0, str(_ROOT))   # for config.*
sys.path.insert(0, str(_ML))     # for pipeline.*

from tqdm import tqdm

from pipeline.utils.logger import StepLogger
from pipeline.utils.db import get_db
from pipeline.nlp.classify import classify_event, analyze_sentiment, neg_score
from pipeline.nlp.ner import extract_countries, intensity_score
from pipeline.nlp.store import (
    ensure_indexes, fetch_unprocessed, save_event, label_distribution,
    prune_orphan_events,
)
from config.settings import settings

log = StepLogger("Step 2 - NLP Processing")


def reset_processed_flags():
    """Mark all raw_articles as unprocessed so step2 re-runs NLP on them."""
    result = get_db()[settings.COL_RAW_ARTICLES].update_many(
        {}, {"$set": {"processed": False}}
    )
    log.info(f"Reset {result.modified_count} articles to unprocessed")


def main(reprocess: bool = False):
    log.header()
    if reprocess:
        log.info("--reprocess flag set: resetting all articles to unprocessed...")
        reset_processed_flags()
    log.info("Loading HuggingFace models (first run downloads ~1 GB)...")

    ensure_indexes()
    articles = fetch_unprocessed(limit=1000)

    if not articles:
        log.warn("No unprocessed articles found.")
        log.info("Run step1_ingest.py first, or all articles are already processed.")
        return

    log.info(f"{len(articles)} articles to process\n")

    processed = errors = 0

    for article in tqdm(articles, desc="  NLP", unit="article"):
        try:
            text = f"{article.get('title', '')} {article.get('description', '')}"

            event_label,  event_score    = classify_event(text)
            sent_label,   sent_score     = analyze_sentiment(text)
            intensity                    = intensity_score(text)
            negativity                   = neg_score(sent_label, sent_score, intensity)
            countries                    = extract_countries(text)

            save_event(
                article,
                event_label, event_score,
                sent_label,  sent_score,
                negativity,  countries,
                intensity,
            )
            processed += 1

        except Exception as e:
            log.error(f"Article '{article.get('title','')[:50]}': {e}")
            errors += 1

    orphans = prune_orphan_events()

    dist = label_distribution()
    dist_str = "  |  ".join(f"{k}: {v}" for k, v in sorted(dist.items()))

    log.footer({
        "Processed":      processed,
        "Errors":         errors,
        "Orphans pruned": orphans,
        "Label dist":     dist_str,
        "Next step":      "python scripts/step3_score.py",
    })


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--reprocess", action="store_true",
        help="Re-run NLP on all articles, not just new ones",
    )
    args = parser.parse_args()
    main(args.reprocess)

