"""
pipeline/forecasting/forecaster.py
────────────────────────────────────
7-day tension forecast using damped Holt's exponential smoothing.

Design rationale:
  - Holt's double exponential smoothing tracks both level and trend separately.
  - Damping factor φ=0.88 causes the trend to fade over the horizon, preventing
    runaway projections (e.g. a recent spike can't keep projecting upward for 7 days).
  - R² of one-step-ahead fitted values vs actuals is used as a confidence signal.
  - Falls back gracefully when data is sparse (< 3 data points).
  - No training required — works immediately on any country with history.

Parameters:
  alpha=0.4  — level smoothing (higher = more weight on recent observations)
  beta=0.2   — trend smoothing (higher = trend adapts faster to changes)
  phi=0.88   — damping: over 7 days the trend shrinks to φ^7 ≈ 0.41× its initial value

Why Holt's over linear regression?
  - Linear regression extrapolates the trend indefinitely — a spike 2 weeks ago
    drives the forecast upward for 7 more days.
  - Holt's level adapts continuously, so recent data always dominates.
  - Damping prevents geopolitically unrealistic projections (e.g. 0.63 → 0.95).
"""

import numpy as np
from datetime import datetime, timedelta
from typing import Optional

from config.settings import settings


# ── History fetching ──────────────────────────────────────────────────────────

def fetch_country_history(db, iso: str, days: int = None) -> list[dict]:
    """
    Fetch last N days of daily_signals for a country, sorted chronologically.

    Returns list of dicts with keys: date, tension_score, conflict_gravity,
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
                "conflict_gravity": 1,
                "event_count": 1,
                "tension_label": 1,
                "avg_neg_sentiment": 1,
                "_id": 0,
            },
        )
        .sort("date", -1)
        .limit(days)
    )
    return list(reversed(docs))


# ── Holt's exponential smoothing ──────────────────────────────────────────────

def _holts_smooth(
    scores: list[float],
    alpha: float = 0.4,
    beta: float  = 0.2,
    phi: float   = 0.88,
) -> tuple[float, float, list[float]]:
    """
    Damped Holt's double exponential smoothing fit pass.

    Returns:
        level   — smoothed level at the last observation
        trend   — smoothed trend at the last observation
        fitted  — one-step-ahead predictions for each observation (same length as scores)
    """
    n = len(scores)

    # Initialise level at first observation; trend from the first few steps
    level = scores[0]
    trend = (scores[min(3, n - 1)] - scores[0]) / min(3, n - 1) if n >= 2 else 0.0

    fitted = [level]  # one-step-ahead for t=0 is just the initial level

    for i in range(1, n):
        # One-step-ahead prediction before updating (what we would have predicted)
        fitted.append(level + phi * trend)

        prev_level = level
        level = alpha * scores[i] + (1 - alpha) * (level + phi * trend)
        trend = beta  * (level - prev_level) + (1 - beta) * phi * trend

    return level, trend, fitted


def _holts_predict(level: float, trend: float, horizon: int, phi: float = 0.88) -> list[float]:
    """
    Project h steps forward using the damped trend.

    forecast(h) = level + (φ + φ² + ... + φ^h) × trend
               = level + φ×(1 − φ^h)/(1 − φ) × trend

    The cumulative sum of φ^1..h means the trend contributes meaningfully
    but is bounded — it can never exceed φ/(1−φ) × trend as h → ∞.
    """
    predictions = []
    phi_power    = phi        # φ^1, φ^2, ...
    phi_cumsum   = 0.0        # running sum of φ^1 + φ^2 + ... + φ^h
    for _ in range(horizon):
        phi_cumsum += phi_power
        raw = level + phi_cumsum * trend
        predictions.append(round(max(0.0, min(1.0, raw)), 4))
        phi_power *= phi
    return predictions


# ── Confidence helpers ────────────────────────────────────────────────────────

def _r_squared(y_actual: np.ndarray, y_fitted: np.ndarray) -> float:
    """Coefficient of determination (R²) of one-step-ahead fitted values."""
    ss_res = float(np.sum((y_actual - y_fitted) ** 2))
    ss_tot = float(np.sum((y_actual - np.mean(y_actual)) ** 2))
    if ss_tot < 1e-10:
        return 1.0
    return max(0.0, 1.0 - ss_res / ss_tot)


def _confidence_level(r2: float, n_points: int) -> tuple[str, str]:
    """Map R² and data count to a human-readable confidence level + note."""
    if n_points < 5:
        return "low", f"Only {n_points} data point(s) — insufficient history"
    if n_points < 10:
        level = "low" if r2 < 0.5 else "medium"
        return level, f"Limited history ({n_points} days)"
    if r2 >= 0.70:
        return "high", "Strong consistent trend in recent data"
    if r2 >= 0.40:
        return "medium", "Moderate trend — some volatility present"
    return "low", "High volatility — trend is inconsistent"


def _direction_label(pct_change: float) -> str:
    if pct_change > 8:
        return "escalating"
    if pct_change < -8:
        return "de-escalating"
    return "stable"


# ── Main entry point ──────────────────────────────────────────────────────────

def compute_forecast(history: list[dict], iso: str = "") -> Optional[dict]:
    """
    Compute a 7-day tension forecast from a country's historical signals
    using damped Holt's exponential smoothing.

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

    # Smooth through all available history
    level, trend, fitted = _holts_smooth(scores)

    # R² of one-step-ahead predictions vs actuals (skip t=0 initialisation point)
    y_actual = np.array(scores[1:], dtype=float)
    y_fitted = np.array(fitted[1:],  dtype=float)
    r2 = _r_squared(y_actual, y_fitted) if len(y_actual) > 1 else 0.0

    # Project forward
    predictions = _holts_predict(level, trend, horizon)

    # Direction and magnitude
    current    = scores[-1]
    future_end = predictions[-1]
    pct_change = ((future_end - current) / max(current, 0.01)) * 100.0

    direction           = _direction_label(pct_change)
    conf_level, conf_note = _confidence_level(r2, n)

    # If the 7-day actual momentum directly contradicts the forecast, flag it.
    if n >= 7:
        recent_change    = scores[-1] - scores[-7]
        momentum_falling = recent_change < -0.05
        momentum_rising  = recent_change >  0.05
        if (pct_change > 8 and momentum_falling) or (pct_change < -8 and momentum_rising):
            conf_level = "low"
            conf_note  = "Forecast conflicts with recent 7-day momentum — treat with caution"

    # Forecast date strings
    try:
        last_dt = datetime.strptime(dates[-1], "%Y-%m-%d")
    except (ValueError, IndexError):
        last_dt = datetime.utcnow()

    forecast_dates = [
        (last_dt + timedelta(days=i)).strftime("%Y-%m-%d")
        for i in range(1, horizon + 1)
    ]

    return {
        "iso":              iso or (history[0].get("iso", "") if history else ""),
        "current_score":    round(current, 4),
        "history_scores":   [round(s, 4) for s in scores[-7:]],
        "history_dates":    dates[-7:],
        "predictions":      predictions,
        "forecast_dates":   forecast_dates,
        "direction":        direction,
        "pct_change":       round(pct_change, 1),
        "slope_per_day":    round(trend, 5),
        "confidence_r2":    round(r2, 3),
        "confidence_level": conf_level,
        "confidence_note":  conf_note,
        "data_points_used": n,
        "computed_at":      datetime.utcnow().isoformat() + "Z",
    }
