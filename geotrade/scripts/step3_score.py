"""
scripts/step3_score.py — Tension Scoring
==========================================
Aggregates processed_events by (date, country).
Computes tension_score = α * neg_sentiment + β * conflict_ratio.
Writes to MongoDB: daily_signals  +  data/processed/daily_signals.csv

Run (from project root):
    python scripts/step3_score.py
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from config.settings import settings
from pipeline.utils.db import get_db
from pipeline.utils.logger import StepLogger
from pipeline.scoring.scorer import compute_signals
from pipeline.scoring.store import upsert_signals, export_csv, tension_stats

log = StepLogger("Step 3 — Tension Scoring")


def main():
    log.header()
    log.info(f"Formula: score = {settings.TENSION_ALPHA}×neg_sentiment "
             f"+ {settings.TENSION_BETA}×conflict_ratio")

    events = list(get_db()[settings.COL_PROCESSED_EVENTS].find({}))
    if not events:
        log.warn("No processed events found. Run step2_nlp.py first.")
        return

    log.info(f"Loaded {len(events)} processed events")

    signals = compute_signals(events)
    log.info(f"Computed {len(signals)} (date × country) signals")

    count   = upsert_signals(signals)
    csv_path = export_csv(signals)
    stats   = tension_stats(signals)

    log.footer({
        "Signals upserted":  count,
        "CSV exported":      csv_path,
        "Score min/mean/max": f"{stats['min']} / {stats['mean']} / {stats['max']}",
        "High / Med / Low":  f"{stats['high']} / {stats['medium']} / {stats['low']}",
        "Next step":         "python scripts/step4_model.py",
    })


if __name__ == "__main__":
    main()
