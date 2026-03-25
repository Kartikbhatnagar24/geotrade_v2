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
