"""
backend/routes/forecast.py
───────────────────────────
GET /forecast/{country_iso}

Returns a 7-day tension score forecast for a country:
  - Sparkline data: last 7 days (actuals) + next 7 days (predicted)
  - Direction badge: escalating | stable | de-escalating
  - % change over forecast window
  - Confidence level (high / medium / low) + note

Caching:
  Results are stored in the tension_forecasts collection.
  Cache is considered fresh for FORECAST_CACHE_MINUTES (default 60).
  On-demand recompute if stale.
"""

from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException

from backend.core.database import get_db
from config.settings import settings
from pipeline.forecasting.forecaster import fetch_country_history, compute_forecast

router = APIRouter(prefix="/forecast", tags=["Forecast"])


def _is_fresh(doc: dict) -> bool:
    """True if the cached forecast is within FORECAST_CACHE_MINUTES."""
    raw = doc.get("computed_at", "")
    if not raw:
        return False
    try:
        dt = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        age_seconds = (datetime.now(timezone.utc) - dt).total_seconds()
        return age_seconds < settings.FORECAST_CACHE_MINUTES * 60
    except ValueError:
        return False


@router.get("/{country_iso}", summary="7-day tension forecast for a country")
def get_forecast(country_iso: str):
    """
    Compute or retrieve a cached 7-day tension forecast for a country.

    Returns:
      - history_scores / history_dates : last 7 days actuals
      - predictions / forecast_dates   : next 7 days projected scores
      - direction                      : escalating | stable | de-escalating
      - pct_change                     : % change from today to day 7
      - confidence_level               : high | medium | low
      - confidence_note                : plain-English explanation
    """
    iso = country_iso.upper()
    db  = get_db()

    # ── 1. Try cache ──────────────────────────────────────────
    cached = db[settings.COL_TENSION_FORECASTS].find_one(
        {"iso": iso}, sort=[("computed_at", -1)]
    )
    if cached and _is_fresh(cached):
        cached.pop("_id", None)
        cached["from_cache"] = True
        return cached

    # ── 2. Fetch history ──────────────────────────────────────
    history = fetch_country_history(db, iso)
    if not history:
        raise HTTPException(
            status_code=404,
            detail=f"No tension history found for '{iso}'. Run pipeline steps 1-3 first.",
        )
    if len(history) < 3:
        raise HTTPException(
            status_code=422,
            detail=(
                f"Only {len(history)} data point(s) for '{iso}' — need at least 3 "
                "to compute a meaningful forecast."
            ),
        )

    # ── 3. Compute forecast ───────────────────────────────────
    result = compute_forecast(history, iso=iso)
    if not result:
        raise HTTPException(
            status_code=500,
            detail=f"Forecast computation failed for '{iso}'.",
        )

    # ── 4. Cache (upsert) ─────────────────────────────────────
    db[settings.COL_TENSION_FORECASTS].replace_one(
        {"iso": iso}, result, upsert=True
    )

    result["from_cache"] = False
    return result
