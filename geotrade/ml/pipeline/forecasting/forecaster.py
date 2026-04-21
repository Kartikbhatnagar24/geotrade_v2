"""
pipeline/forecasting/forecaster.py
────────────────────────────────────
7-day tension forecast using numpy linear trend extrapolation.

Design rationale:
  - Uses polynomial fit (degree 1 = linear) on the last 14 days of tension scores.
  - Projects 7 days forward and clips to [0, 1].
  - R² of the fit is used as a confidence signal.
  - Falls back gracefully when data is sparse (< 3 data points).
  - No training required — works immediately on any country with history.

Why not LightGBM here?
  - Many countries have < 30 data points, insufficient for per-country ML training.
  - A cross-country LightGBM model can be layered on top later (step5b).
  - Linear trend gives interpretable, honest forecasts for now.
"""

import numpy as np
from datetime import datetime, timedelta
from typing import Optional

from config.settings import settings


# ── History fetching ──────────────────────────────────────────────────────────

def fetch_country_history(db, iso: str, days: int = None) -> list[dict]:
    """
    Fetch last N days of daily_signals for a country, sorted chronologically.

    Returns list of dicts with keys: date, tension_score, conflict_ratio,
    event_count, tension_label.
    """
    days = days or settings.FORECAST_HISTORY_DAYS
    docs = list(
        db[settings.COL_DAILY_SIGNALS]
        .find(
            {"iso": iso.upper()},
            {
                "date": 1,
                "tension_score": 1,
                "conflict_ratio": 1,
                "event_count": 1,
                "tension_label": 1,
                "avg_neg_sentiment": 1,
                "_id": 0,
            },
        )
        .sort("date", -1)
        .limit(days)
    )
    # Return in chronological order (oldest → newest)
    return list(reversed(docs))


# ── Core forecast engine ──────────────────────────────────────────────────────

def _r_squared(y_actual: np.ndarray, y_fitted: np.ndarray) -> float:
    """Coefficient of determination (R²). Returns 0 if undefined."""
    ss_res = float(np.sum((y_actual - y_fitted) ** 2))
    ss_tot = float(np.sum((y_actual - np.mean(y_actual)) ** 2))
    if ss_tot < 1e-10:
        return 1.0  # perfect flat line — maximum consistency
    return max(0.0, 1.0 - ss_res / ss_tot)


def _confidence_level(r2: float, n_points: int) -> tuple[str, str]:
    """Map R² and data count to a human-readable confidence level + note."""
    if n_points < 5:
        return "low", f"Only {n_points} data point(s) — insufficient history"
    if n_points < 10:
        note = f"Limited history ({n_points} days)"
        level = "low" if r2 < 0.5 else "medium"
        return level, note
    # Enough data — use R² to determine quality
    if r2 >= 0.70:
        return "high", "Strong consistent trend in recent data"
    if r2 >= 0.40:
        return "medium", "Moderate trend — some volatility present"
    return "low", "High volatility — trend is inconsistent"


def _direction_label(pct_change: float) -> str:
    """Classify direction from percentage change over forecast window."""
    if pct_change > 8:
        return "escalating"
    if pct_change < -8:
        return "de-escalating"
    return "stable"


def compute_forecast(history: list[dict], iso: str = "") -> Optional[dict]:
    """
    Compute a 7-day tension forecast from a country's historical signals.

    Args:
        history: chronologically sorted list of daily_signal dicts
        iso:     country ISO code (for labelling)

    Returns:
        dict with keys:
            iso, current_score, history_scores, history_dates,
            predictions, forecast_dates,
            direction, pct_change,
            confidence_r2, confidence_level, confidence_note,
            data_points_used, computed_at
        or None if data is insufficient.
    """
    if not history:
        return None

    horizon = settings.FORECAST_HORIZON_DAYS
    scores  = [float(h.get("tension_score", 0.5)) for h in history]
    dates   = [h.get("date", "") for h in history]
    n       = len(scores)

    # Use at most last 14 days for the fit window (more recent = more relevant)
    fit_window = min(14, n)
    y = np.array(scores[-fit_window:], dtype=float)
    x = np.arange(fit_window, dtype=float)

    # Linear polynomial fit
    coeffs = np.polyfit(x, y, deg=1)  # [slope, intercept]
    slope  = float(coeffs[0])

    # R² on the fitted window
    y_fitted = np.polyval(coeffs, x)
    r2       = _r_squared(y, y_fitted)

    # Project horizon days forward
    base_x = float(fit_window - 1)
    predictions: list[float] = []
    for i in range(1, horizon + 1):
        raw = float(np.polyval(coeffs, base_x + i))
        predictions.append(round(max(0.0, min(1.0, raw)), 4))

    # Direction + magnitude
    current      = scores[-1]
    future_end   = predictions[-1]
    pct_change   = ((future_end - current) / max(current, 0.01)) * 100.0

    direction           = _direction_label(pct_change)
    conf_level, conf_note = _confidence_level(r2, n)

    # Generate forecast date strings
    try:
        last_dt = datetime.strptime(dates[-1], "%Y-%m-%d")
    except (ValueError, IndexError):
        last_dt = datetime.utcnow()

    forecast_dates = [
        (last_dt + timedelta(days=i)).strftime("%Y-%m-%d")
        for i in range(1, horizon + 1)
    ]

    return {
        "iso":               iso or (history[0].get("iso", "") if history else ""),
        "current_score":     round(current, 4),
        # Last 7 days of actuals for the sparkline context bar
        "history_scores":    [round(s, 4) for s in scores[-7:]],
        "history_dates":     dates[-7:],
        "predictions":       predictions,
        "forecast_dates":    forecast_dates,
        "direction":         direction,
        "pct_change":        round(pct_change, 1),
        "slope_per_day":     round(slope, 5),
        "confidence_r2":     round(r2, 3),
        "confidence_level":  conf_level,
        "confidence_note":   conf_note,
        "data_points_used":  n,
        "computed_at":       datetime.utcnow().isoformat() + "Z",
    }
