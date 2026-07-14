"""
scripts/step3_score.py â€” Tension Scoring
==========================================
Aggregates processed_events by (date, country).
Computes tension_score = α * neg_sentiment + β * conflict_gravity + γ * coverage_signal.
Writes to MongoDB: daily_signals  +  data/processed/daily_signals.csv

Run (from project root):
    python scripts/step3_score.py
"""

import sys
from pathlib import Path
_ML = Path(__file__).resolve().parent.parent        # geotrade/ml
_ROOT = _ML.parent                                   # geotrade
sys.path.insert(0, str(_ROOT))   # for config.*
sys.path.insert(0, str(_ML))     # for pipeline.*

from config.settings import settings
from pipeline.utils.db import get_db
from pipeline.utils.logger import StepLogger
from pipeline.scoring.scorer import compute_signals
from pipeline.scoring.store import (
    upsert_signals, export_csv, tension_stats, reconcile_signals,
)

log = StepLogger("Step 3 â€” Tension Scoring")


def main():
    log.header()
    log.info(f"Formula: score = {settings.TENSION_ALPHA}×neg_sentiment "
             f"+ {settings.TENSION_BETA}×conflict_gravity "
             f"+ {settings.TENSION_GAMMA}×coverage_signal")

    events = list(get_db()[settings.COL_PROCESSED_EVENTS].find({}))
    if not events:
        log.warn("No processed events found. Run step2_nlp.py first.")
        return

    log.info(f"Loaded {len(events)} processed events")

    signals = compute_signals(events)
    log.info(f"Computed {len(signals)} (date Ã— country) signals")

    count   = upsert_signals(signals)
    cleanup = reconcile_signals(signals)
    csv_path = export_csv(signals)
    stats   = tension_stats(signals)

    log.footer({
        "Signals upserted":  count,
        "WLD removed":       cleanup["wld_deleted"],
        "Old (>180d) removed": cleanup["old_deleted"],
        "Stale pairs removed": cleanup["stale_pair_deleted"],
        "CSV exported":      csv_path,
        "Score min/mean/max": f"{stats['min']} / {stats['mean']} / {stats['max']}",
        "High / Med / Low":  f"{stats['high']} / {stats['medium']} / {stats['low']}",
        "Next step":         "python scripts/step4_model.py",
    })


if __name__ == "__main__":
    main()

