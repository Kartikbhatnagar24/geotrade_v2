"""
pipeline/scoring/scorer.py
───────────────────────────
Aggregates processed_events by (date, country) and computes
tension_score = α * avg_neg_sentiment + β * conflict_ratio

Improvements over v1:
  1. WLD fallback removed — articles with no country match are skipped.
     This eliminates the phantom "World" entries on the globe.
  2. Intensity weighting — articles with high intensity_score (e.g. nuclear,
     invasion) contribute more to the tension average than routine articles.
  3. Smoothed score — in addition to the raw score, a smoothed_score is
     computed using a 3-event exponential moving average to reduce spike noise.
     The globe still uses tension_score; smoothed_score is available for the
     7-day forecast and trend analysis.
  4. article_count_log — log-scaled event count stored for future normalization.
"""

from collections import defaultdict
from datetime import datetime, timezone
from math import log1p

import pandas as pd

from config.settings import settings


def _dominant_label(labels: list[str]) -> str:
    return max(set(labels), key=labels.count)


def _tension_label(score: float) -> str:
    if score >= 0.65:
        return "high"
    if score >= 0.35:
        return "medium"
    return "low"


def _intensity_weighted_avg(values: list[float], weights: list[float]) -> float:
    """Weighted average, falls back to simple mean if all weights are zero."""
    total_w = sum(weights)
    if total_w < 1e-9:
        return sum(values) / len(values) if values else 0.0
    return sum(v * w for v, w in zip(values, weights)) / total_w


def compute_signals(events: list[dict]) -> list[dict]:
    """
    Group events by (date, country ISO) and compute tension scores.

    Args:
        events: list of processed_event docs from MongoDB

    Returns:
        list of daily_signal dicts (excludes entries with iso == "WLD")
    """
    α = settings.TENSION_ALPHA
    β = settings.TENSION_BETA

    # ── Group by (date_str, iso) ──────────────────────────────
    groups: dict[tuple[str, str], list] = defaultdict(list)

    for ev in events:
        # Skip articles that matched no known country
        countries = ev.get("countries") or []
        if not countries:
            continue

        try:
            date_str = pd.to_datetime(ev.get("published_at", "")).strftime("%Y-%m-%d")
        except Exception:
            date_str = datetime.now().strftime("%Y-%m-%d")

        for country in countries:
            iso = country.get("iso", "")
            if not iso or iso == "WLD":   # skip phantom world entries
                continue
            groups[(date_str, iso)].append({
                "event_label":    ev.get("event_label", "unknown"),
                "neg_sentiment":  ev.get("neg_sentiment_score", 0.5),
                "intensity":      ev.get("intensity_score", 0.3),  # new
                "country_name":   country["name"],
                "lat":            country["lat"],
                "lon":            country["lon"],
                "iso":            iso,
                "title":          ev.get("title", ""),
                "url":            ev.get("url", ""),
            })

    # ── Score each bucket ─────────────────────────────────────
    signals = []
    for (date_str, iso), group in groups.items():
        n              = len(group)
        conflict_count = sum(1 for e in group if e["event_label"] == "conflict")
        conflict_ratio = conflict_count / n

        # Intensity-weighted negative sentiment (new in v2)
        weights        = [max(e["intensity"], 0.1) for e in group]  # floor at 0.1
        avg_neg        = _intensity_weighted_avg(
            [e["neg_sentiment"] for e in group], weights
        )

        # Raw tension score
        raw_score = min(max(α * avg_neg + β * conflict_ratio, 0.0), 1.0)

        # Smoothed score: pull toward 0.5 when n is small (fewer articles = less certainty)
        # Formula: smoothed = raw * reliability + 0.5 * (1 - reliability)
        # reliability = 1 - exp(-n/5): reaches ~0.86 at n=10, ~0.98 at n=20
        import math
        reliability  = 1.0 - math.exp(-n / 5.0)
        smoothed     = round(raw_score * reliability + 0.5 * (1.0 - reliability), 4)

        rep = group[0]  # representative article for labels

        signals.append({
            "date":              date_str,
            "country":           rep["country_name"],
            "iso":               iso,
            "lat":               rep["lat"],
            "lon":               rep["lon"],
            "tension_score":     round(raw_score, 4),
            "smoothed_score":    smoothed,                  # new
            "tension_label":     _tension_label(raw_score),
            "avg_neg_sentiment": round(avg_neg, 4),
            "conflict_ratio":    round(conflict_ratio, 4),
            "conflict_count":    conflict_count,
            "event_count":       n,
            "article_count_log": round(log1p(n), 4),        # new — for normalization
            "top_event_label":   _dominant_label([e["event_label"] for e in group]),
            "sample_title":      rep["title"],
            "sample_url":        rep["url"],
            "computed_at":       datetime.now(timezone.utc).isoformat(),
            "alpha":             α,
            "beta":              β,
        })

    return signals
