"""
backend/models/schemas.py
──────────────────────────
Pydantic models for all API response shapes.
FastAPI uses these for validation, serialization, and /docs.
"""

from typing import Optional
from pydantic import BaseModel


# ── /events ──────────────────────────────────────────────────

class EventPoint(BaseModel):
    country:       str
    iso:           str
    latitude:      float
    longitude:     float
    tension_score: float
    tension_label: str          # high | medium | low
    event_label:   str          # conflict | diplomacy | sanctions | elections | trade
    event_count:   int
    date:          str
    sample_title:  str
    sample_url:    str


class EventsResponse(BaseModel):
    count:  int
    events: list[EventPoint]


# ── /signals ──────────────────────────────────────────────────

class DailySignal(BaseModel):
    date:               str
    global_tension:     float
    max_tension:        float
    total_events:       int
    countries_affected: int


class SignalsResponse(BaseModel):
    count:   int
    signals: list[DailySignal]


# ── /stats ───────────────────────────────────────────────────

class CollectionCounts(BaseModel):
    raw_articles:     int
    processed_events: int
    daily_signals:    int


class CountryEntry(BaseModel):
    country:     str
    iso:         str
    avg_tension: float


class StatsResponse(BaseModel):
    counts:                   CollectionCounts
    event_labels:             dict[str, int]
    tension_labels:           dict[str, int]
    top_countries_by_tension: list[CountryEntry]


# ── /health ───────────────────────────────────────────────────

class HealthResponse(BaseModel):
    status:      str
    mongodb:     str
    collections: dict[str, int]


# ── /forecast ────────────────────────────────────────────────

class ForecastResponse(BaseModel):
    iso:               str
    current_score:     float
    history_scores:    list[float]   # last 7 actuals
    history_dates:     list[str]
    predictions:       list[float]   # next 7 projected
    forecast_dates:    list[str]
    direction:         str           # escalating | stable | de-escalating
    pct_change:        float         # % change today → day 7
    slope_per_day:     float
    confidence_r2:     float
    confidence_level:  str           # high | medium | low
    confidence_note:   str
    data_points_used:  int
    computed_at:       str
    from_cache:        Optional[bool] = None


# ── /briefing ────────────────────────────────────────────────

class TradeIdea(BaseModel):
    asset:     str
    direction: str          # LONG | SHORT
    reasoning: str


class BriefingAnalysis(BaseModel):
    geopolitical_summary: str
    market_impact:        str
    affected_assets:      list[str]
    trade_ideas:          list[TradeIdea]
    risk_level:           str          # high | medium | low
    confidence_note:      str


class TensionSnapshot(BaseModel):
    score: Optional[float] = None
    label: Optional[str]  = None
    date:  Optional[str]  = None


class BriefingResponse(BaseModel):
    iso:              str
    country:          str
    tension_snapshot: TensionSnapshot
    analysis:         BriefingAnalysis
    created_at:       str
    model:            str
    from_cache:       Optional[bool] = None
