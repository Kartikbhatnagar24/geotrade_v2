"""
pipeline/scoring/scorer.py
───────────────────────────
Aggregates processed_events by (date, country) and computes
tension_score = α * avg_neg_sentiment + β * conflict_ratio

Returns a list of signal dicts ready for MongoDB insertion.
"""

from collections import defaultdict
from datetime import datetime, timezone

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


def compute_signals(events: list[dict]) -> list[dict]:
    """
    Group events by (date, country ISO) and compute tension scores.

    Args:
        events: list of processed_event docs from MongoDB

    Returns:
        list of daily_signal dicts
    """
    α = settings.TENSION_ALPHA
    β = settings.TENSION_BETA

    # ── Group by (date_str, iso) ──────────────────────────────
    groups: dict[tuple[str, str], list] = defaultdict(list)

    for ev in events:
        try:
            date_str = pd.to_datetime(ev.get("published_at", "")).strftime("%Y-%m-%d")
        except Exception:
            date_str = datetime.now().strftime("%Y-%m-%d")

        countries = ev.get("countries") or [
            {"name": "World", "lat": 0.0, "lon": 0.0, "iso": "WLD"}
        ]
        for country in countries:
            groups[(date_str, country["iso"])].append({
                "event_label":       ev.get("event_label", "unknown"),
                "neg_sentiment":     ev.get("neg_sentiment_score", 0.5),
                "country_name":      country["name"],
                "lat":               country["lat"],
                "lon":               country["lon"],
                "iso":               country["iso"],
                "title":             ev.get("title", ""),
                "url":               ev.get("url", ""),
            })

    # ── Score each bucket ─────────────────────────────────────
    signals = []
    for (date_str, iso), group in groups.items():
        n                = len(group)
        conflict_count   = sum(1 for e in group if e["event_label"] == "conflict")
        conflict_ratio   = conflict_count / n
        avg_neg          = sum(e["neg_sentiment"] for e in group) / n
        raw_score        = min(max(α * avg_neg + β * conflict_ratio, 0.0), 1.0)
        rep              = group[0]

        signals.append({
            "date":             date_str,
            "country":          rep["country_name"],
            "iso":              iso,
            "lat":              rep["lat"],
            "lon":              rep["lon"],
            "tension_score":    round(raw_score, 4),
            "tension_label":    _tension_label(raw_score),
            "avg_neg_sentiment": round(avg_neg, 4),
            "conflict_ratio":   round(conflict_ratio, 4),
            "conflict_count":   conflict_count,
            "event_count":      n,
            "top_event_label":  _dominant_label([e["event_label"] for e in group]),
            "sample_title":     rep["title"],
            "sample_url":       rep["url"],
            "computed_at":      datetime.now(timezone.utc).isoformat(),
            "alpha":            α,
            "beta":             β,
        })

    return signals
