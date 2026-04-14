"""
scripts/step2_nlp.py — NLP Processing
=======================================
Reads unprocessed articles from raw_articles.
Runs: event classification + sentiment analysis + country NER.
Writes results to MongoDB: processed_events

Run (from project root):
    python scripts/step2_nlp.py
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from tqdm import tqdm

from pipeline.utils.logger import StepLogger
from pipeline.nlp.classify import classify_event, analyze_sentiment, neg_score
from pipeline.nlp.ner import extract_countries, intensity_score
from pipeline.nlp.store import (
    ensure_indexes, fetch_unprocessed, save_event, label_distribution,
)

log = StepLogger("Step 2 — NLP Processing")


def main():
    log.header()
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
            negativity                   = neg_score(sent_label, sent_score)
            countries                    = extract_countries(text)
            intensity                    = intensity_score(text)

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

    dist = label_distribution()
    dist_str = "  |  ".join(f"{k}: {v}" for k, v in sorted(dist.items()))

    log.footer({
        "Processed":      processed,
        "Errors":         errors,
        "Label dist":     dist_str,
        "Next step":      "python scripts/step3_score.py",
    })


if __name__ == "__main__":
    main()
