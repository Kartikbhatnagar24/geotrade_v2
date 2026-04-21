"""
scripts/step5_forecast.py
──────────────────────────
Pre-compute 7-day tension forecasts for all countries that have
data in daily_signals and write them to the tension_forecasts collection.

Run after step3_score.py:
    python scripts/step5_forecast.py

This is optional — the API endpoint /forecast/{iso} will compute
forecasts on-demand and cache them. This script lets you pre-warm
the cache for all known countries at once.
"""

import sys
from pathlib import Path

_ML = Path(__file__).resolve().parent.parent        # geotrade/ml
_ROOT = _ML.parent                                   # geotrade
sys.path.insert(0, str(_ROOT))   # for config.* and backend.*
sys.path.insert(0, str(_ML))     # for pipeline.*

from backend.core.database import get_db
from config.settings import settings
from pipeline.forecasting.forecaster import fetch_country_history, compute_forecast


def run():
    db = get_db()

    # Find all distinct ISOs in daily_signals
    iso_list = db[settings.COL_DAILY_SIGNALS].distinct("iso")
    print(f"[step5] Found {len(iso_list)} countries in daily_signals")

    success, skipped, errors = 0, 0, 0

    for iso in sorted(iso_list):
        try:
            history = fetch_country_history(db, iso)
            if len(history) < 3:
                print(f"  [SKIP] {iso} — only {len(history)} data points, need ≥ 3")
                skipped += 1
                continue

            result = compute_forecast(history, iso=iso)
            if not result:
                print(f"  [SKIP] {iso} — forecast returned None")
                skipped += 1
                continue

            # Upsert by iso (replace previous forecast)
            db[settings.COL_TENSION_FORECASTS].replace_one(
                {"iso": iso},
                result,
                upsert=True,
            )

            direction_arrow = "↑" if result["direction"] == "escalating" else \
                              "↓" if result["direction"] == "de-escalating" else "→"
            print(
                f"  [OK] {iso:4s}  current={result['current_score']:.3f}"
                f"  7d={result['predictions'][-1]:.3f}"
                f"  {direction_arrow}{result['pct_change']:+.1f}%"
                f"  conf={result['confidence_level']}"
                f"  (n={result['data_points_used']})"
            )
            success += 1

        except Exception as exc:
            print(f"  [ERR] {iso} — {exc}")
            errors += 1

    print(f"\n[step5] Done — {success} forecasts written, {skipped} skipped, {errors} errors")

    # Create TTL-style index so old forecasts can be cleaned up
    db[settings.COL_TENSION_FORECASTS].create_index(
        "computed_at",
        name="computed_at_ttl",
        expireAfterSeconds=7 * 24 * 3600,  # auto-delete after 7 days
    )
    print("[step5] TTL index ensured on tension_forecasts.computed_at")


if __name__ == "__main__":
    run()
