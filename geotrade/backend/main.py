"""
backend/main.py
────────────────
FastAPI application entry point.

Run from project root:
    uvicorn backend.main:app --reload --port 8000

API docs:
    http://localhost:8000/docs
"""

import sys
from pathlib import Path

# Ensure project root is on sys.path so config/ resolves correctly
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.core.database import get_db, ping
from backend.routes.events import router as events_router
from backend.routes.signals import router as signals_router
from backend.routes.trading import router as trading_router
from config.settings import settings

# ── App ───────────────────────────────────────────────────────
app = FastAPI(
    title="GeoTrade API",
    description="Geopolitical tension signals for the 3D globe frontend.",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
)

# ── CORS ──────────────────────────────────────────────────────
# Allows the Next.js dev server (localhost:3000) to call this API.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://127.0.0.1:3000"],
    allow_credentials=True,
    allow_methods=["GET"],
    allow_headers=["*"],
)

# ── Routers ───────────────────────────────────────────────────
app.include_router(events_router)
app.include_router(signals_router)
app.include_router(trading_router)


# ── Health / system routes ────────────────────────────────────
@app.get("/health", tags=["System"])
def health():
    """Check API + MongoDB connectivity."""
    db_ok = ping()
    counts: dict = {}
    if db_ok:
        db = get_db()
        counts = {
            "raw_articles":     db[settings.COL_RAW_ARTICLES].count_documents({}),
            "processed_events": db[settings.COL_PROCESSED_EVENTS].count_documents({}),
            "daily_signals":    db[settings.COL_DAILY_SIGNALS].count_documents({}),
        }
    return {
        "status":      "ok" if db_ok else "degraded",
        "mongodb":     "connected" if db_ok else "unreachable",
        "collections": counts,
    }


@app.get("/stats", tags=["System"])
def stats():
    """Pipeline statistics — event label distribution, top countries."""
    db = get_db()

    label_dist = {
        r["_id"]: r["count"]
        for r in db[settings.COL_PROCESSED_EVENTS].aggregate([
            {"$group": {"_id": "$event_label", "count": {"$sum": 1}}}
        ])
    }

    tension_dist = {
        r["_id"]: r["count"]
        for r in db[settings.COL_DAILY_SIGNALS].aggregate([
            {"$group": {"_id": "$tension_label", "count": {"$sum": 1}}}
        ])
    }

    top_countries = list(db[settings.COL_DAILY_SIGNALS].aggregate([
        {"$group": {
            "_id":         "$country",
            "iso":         {"$first": "$iso"},
            "avg_tension": {"$avg": "$tension_score"},
        }},
        {"$sort": {"avg_tension": -1}},
        {"$limit": 10},
    ]))

    return {
        "counts": {
            "raw_articles":     db[settings.COL_RAW_ARTICLES].count_documents({}),
            "processed_events": db[settings.COL_PROCESSED_EVENTS].count_documents({}),
            "daily_signals":    db[settings.COL_DAILY_SIGNALS].count_documents({}),
        },
        "event_labels":  label_dist,
        "tension_labels": tension_dist,
        "top_countries_by_tension": [
            {"country": r["_id"], "iso": r["iso"], "avg_tension": round(r["avg_tension"], 4)}
            for r in top_countries
        ],
    }
