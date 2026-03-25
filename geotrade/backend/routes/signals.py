"""
backend/routes/signals.py
──────────────────────────
GET /signals — daily global tension time series (for charting)
"""

from typing import Optional
from fastapi import APIRouter, Query
from backend.core.database import get_db
from config.settings import settings

router = APIRouter(prefix="/signals", tags=["Signals"])


@router.get("")
def list_signals(
    date_from: Optional[str] = Query(None, description="YYYY-MM-DD"),
    date_to:   Optional[str] = Query(None, description="YYYY-MM-DD"),
    limit:     int           = Query(200, le=1000),
):
    """Global daily tension aggregated across all countries."""
    match: dict = {}
    if date_from or date_to:
        df: dict = {}
        if date_from: df["$gte"] = date_from
        if date_to:   df["$lte"] = date_to
        match["date"] = df

    pipeline = [
        {"$match": match},
        {"$group": {
            "_id":            "$date",
            "global_tension": {"$avg": "$tension_score"},
            "max_tension":    {"$max": "$tension_score"},
            "total_events":   {"$sum": "$event_count"},
            "countries":      {"$sum": 1},
        }},
        {"$sort": {"_id": 1}},
        {"$limit": limit},
    ]

    results = list(get_db()[settings.COL_DAILY_SIGNALS].aggregate(pipeline))
    signals = [
        {
            "date":               r["_id"],
            "global_tension":     round(r["global_tension"], 4),
            "max_tension":        round(r["max_tension"], 4),
            "total_events":       r["total_events"],
            "countries_affected": r["countries"],
        }
        for r in results
    ]
    return {"count": len(signals), "signals": signals}
