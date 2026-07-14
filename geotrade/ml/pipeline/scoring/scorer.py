"""
pipeline/scoring/scorer.py
───────────────────────────
Aggregates processed_events by (date, country) and computes
tension_score = α * avg_neg_sentiment + β * conflict_gravity + γ * coverage_signal

Formula grounding (literature):
  - neg_sentiment : intensity-weighted DistilBERT score (existing)
  - conflict_gravity : Goldstein-scale-inspired continuous event weight, replaces
      the old binary conflict_ratio. Weights derived from CAMEO/Goldstein
      psychophysical magnitude scaling (Schrodt & Gerner; GDELT codebook):
        conflict  → 1.00  (≈ −10 on Goldstein: armed attack)
        military  → 0.80  (≈ −8:  military assault / mobilisation)
        sanctions → 0.50  (≈ −6:  economic coercion)
        diplomacy → 0.10  (≈ −2:  verbal criticism / demand)
        trade     → 0.00  (neutral)
        elections → 0.00  (neutral)
        unknown   → 0.20  (conservative fallback)
      Each label weight is further scaled by the article's intensity_score so
      a "conflict" article with intensity 0.9 contributes more than one at 0.2.
  - coverage_signal : log1p(n) / log1p(COVERAGE_NORM_N), capped at 1.0.
      Inspired by BBVA Research (2025) tone × normalized_coverage product and
      the Caldara-Iacoviello GPR share-of-total-articles normalisation.
      Rewards buckets with many corroborating articles; dampens single-article
      spikes without the sharp reliability cliff of the old exp(-n/5) smoother.

Ref: Caldara & Iacoviello (2022) AER 112(4); GDELT Codebook V2.0;
     Schrodt (CAMEO scaling); BBVA WP 25/14.
"""

from collections import defaultdict
from datetime import datetime, timezone
from math import exp, log1p

import pandas as pd

from config.settings import settings

# ── Goldstein-inspired label → gravity weight ─────────────────────────────────
# Scale: 0.0 (neutral/cooperative) → 1.0 (maximum conflict)
# Mirrors the CAMEO/Goldstein −10…+10 range, linearly mapped to [0, 1].
_LABEL_GRAVITY: dict[str, float] = {
    "conflict":   1.00,
    "military":   0.80,
    "sanctions":  0.50,
    "diplomacy":  0.10,
    "trade":      0.00,
    "elections":  0.00,
    "unknown":    0.20,
}

# Normalisation denominator for coverage signal: log1p(50) ≈ 3.93
# A bucket with ≥50 articles gets full coverage credit (1.0).
_COVERAGE_NORM_N: int = 50


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


def _conflict_gravity(group: list[dict]) -> float:
    """
    Continuous Goldstein-style conflict signal for a bucket of articles.

    Each article contributes: label_weight × intensity (floored at 0.1).
    The sum is normalised by n so the result stays in [0, 1].
    """
    n = len(group)
    if n == 0:
        return 0.0
    total = sum(
        _LABEL_GRAVITY.get(e["event_label"], 0.2) * max(e["intensity"], 0.1)
        for e in group
    )
    return min(total / n, 1.0)


def compute_signals(events: list[dict]) -> list[dict]:
    """
    Group events by (date, country ISO) and compute tension scores.

    Args:
        events: list of processed_event docs from MongoDB

    Returns:
        list of daily_signal dicts (excludes entries with iso == "WLD")
    """
    α = settings.TENSION_ALPHA   # weight for neg_sentiment    (default 0.5)
    β = settings.TENSION_BETA    # weight for conflict_gravity  (default 0.35)
    γ = settings.TENSION_GAMMA   # weight for coverage_signal   (default 0.15)

    # ── Group by (date_str, iso) ──────────────────────────────
    groups: dict[tuple[str, str], list] = defaultdict(list)

    for ev in events:
        countries = ev.get("countries") or []
        if not countries:
            continue

        try:
            date_str = pd.to_datetime(ev.get("published_at", "")).strftime("%Y-%m-%d")
        except Exception:
            date_str = datetime.now().strftime("%Y-%m-%d")

        for country in countries:
            iso = country.get("iso", "")
            if not iso or iso == "WLD":
                continue
            groups[(date_str, iso)].append({
                "event_label":  ev.get("event_label", "unknown"),
                "neg_sentiment": ev.get("neg_sentiment_score", 0.5),
                "intensity":    ev.get("intensity_score", 0.3),
                "country_name": country["name"],
                "lat":          country["lat"],
                "lon":          country["lon"],
                "iso":          iso,
                "title":        ev.get("title", ""),
                "url":          ev.get("url", ""),
            })

    # ── Score each bucket ─────────────────────────────────────
    signals = []
    for (date_str, iso), group in groups.items():
        n = len(group)

        # 1. Intensity-weighted negative sentiment
        weights = [max(e["intensity"], 0.1) for e in group]
        avg_neg = _intensity_weighted_avg(
            [e["neg_sentiment"] for e in group], weights
        )

        # 2. Goldstein-inspired conflict gravity (replaces binary conflict_ratio)
        gravity = _conflict_gravity(group)

        # 3. Coverage signal — rewards corroboration, dampens single-article spikes
        coverage = min(log1p(n) / log1p(_COVERAGE_NORM_N), 1.0)

        # 4. Raw tension score
        raw_score = min(max(α * avg_neg + β * gravity + γ * coverage, 0.0), 1.0)

        # 5. Smoothed score — pull toward 0.5 when coverage is thin
        #    reliability = 1 - exp(-n/5): ~0.86 at n=10, ~0.98 at n=20
        reliability = 1.0 - exp(-n / 5.0)
        smoothed    = round(raw_score * reliability + 0.5 * (1.0 - reliability), 4)

        rep = group[0]

        signals.append({
            "date":              date_str,
            "country":           rep["country_name"],
            "iso":               iso,
            "lat":               rep["lat"],
            "lon":               rep["lon"],
            "tension_score":     round(raw_score, 4),
            "smoothed_score":    smoothed,
            "tension_label":     _tension_label(raw_score),
            "avg_neg_sentiment": round(avg_neg, 4),
            "conflict_gravity":  round(gravity, 4),   # replaces conflict_ratio
            "coverage_signal":   round(coverage, 4),  # new
            "event_count":       n,
            "article_count_log": round(log1p(n), 4),
            "top_event_label":   _dominant_label([e["event_label"] for e in group]),
            "sample_title":      rep["title"],
            "sample_url":        rep["url"],
            "computed_at":       datetime.now(timezone.utc).isoformat(),
            "alpha":             α,
            "beta":              β,
            "gamma":             γ,
        })

    return signals
