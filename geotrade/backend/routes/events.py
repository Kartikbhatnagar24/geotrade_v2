"""
backend/routes/events.py
─────────────────────────
GET /events          — all signals with lat/lon (consumed by globe)
GET /events/{iso}    — signals for one country ISO code
"""

from typing import Optional
from fastapi import APIRouter, Query, HTTPException
from backend.core.database import get_db
from config.settings import settings

router = APIRouter(prefix="/events", tags=["Events"])


def _to_event(doc: dict) -> dict:
    return {
        "country":       doc.get("country", ""),
        "iso":           doc.get("iso", ""),
        "latitude":      doc.get("lat", 0.0),
        "longitude":     doc.get("lon", 0.0),
        "tension_score": doc.get("tension_score", 0.0),
        "tension_label": doc.get("tension_label", "low"),
        "event_label":   doc.get("top_event_label", "unknown"),
        "event_count":   doc.get("event_count", 0),
        "date":          doc.get("date", ""),
        "sample_title":  doc.get("sample_title", ""),
        "sample_url":    doc.get("sample_url", ""),
    }


@router.get("")
def list_events(
    tension_label: Optional[str] = Query(None, description="high | medium | low"),
    date_from:     Optional[str] = Query(None, description="YYYY-MM-DD"),
    date_to:       Optional[str] = Query(None, description="YYYY-MM-DD"),
    limit:         int           = Query(500, le=2000),
):
    """Return geopolitical events with coordinates and tension scores."""
    query: dict = {}
    if tension_label:
        query["tension_label"] = tension_label
    if date_from or date_to:
        df: dict = {}
        if date_from: df["$gte"] = date_from
        if date_to:   df["$lte"] = date_to
        query["date"] = df

    pipeline: list = []
    if query:
        pipeline.append({"$match": query})
    pipeline += [
        {"$sort": {"date": -1, "tension_score": -1}},
        {"$group": {"_id": "$iso", "doc": {"$first": "$$ROOT"}}},
        {"$replaceRoot": {"newRoot": "$doc"}},
        {"$sort": {"tension_score": -1}},
        {"$limit": limit},
        {"$project": {"_id": 0}},
    ]
    docs = list(get_db()[settings.COL_DAILY_SIGNALS].aggregate(pipeline))
    return {"count": len(docs), "events": [_to_event(d) for d in docs]}


@router.get("/{country_iso}")
def get_country_events(country_iso: str):
    """Return all signals for a specific country ISO (e.g. US, RU, CN)."""
    docs = list(
        get_db()[settings.COL_DAILY_SIGNALS]
        .find({"iso": country_iso.upper()}, {"_id": 0})
        .sort("date", -1)
    )
    if not docs:
        raise HTTPException(404, f"No signals found for: {country_iso.upper()}")
    return {"country_iso": country_iso.upper(), "count": len(docs), "signals": docs}
