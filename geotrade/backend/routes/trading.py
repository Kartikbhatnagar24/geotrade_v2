"""
backend/routes/trading.py
──────────────────────────
GET /trading/{country_iso}
  Returns stock/ETF trade signals + tension context + model prediction.

Fixed (2026-03):
  - _get_recent_news: processed_events stores iso inside countries[].iso
    → query uses {"countries.iso": iso} and sorts by published_at
  - _get_latest_tension: daily_signals has iso at root level (correct)
"""

from fastapi import APIRouter, HTTPException
from backend.core.database import get_db
from config.settings import settings
from pipeline.scoring.stocks import get_stock_signals
from pipeline.nlp.classifier import classify_news_type

router = APIRouter(prefix="/trading", tags=["Trading"])


def _get_latest_tension(db, iso: str) -> dict:
    """Pull the latest daily signal for this country from MongoDB.
    daily_signals stores iso at root level — correct as-is."""
    doc = db[settings.COL_DAILY_SIGNALS].find_one(
        {"iso": iso.upper()},
        sort=[("date", -1)],
    )
    if not doc:
        return {}
    return {
        "tension_score":     doc.get("tension_score", 0.5),
        "tension_label":     doc.get("tension_label", "medium"),
        "date":              doc.get("date", ""),
        "event_count":       doc.get("event_count", 0),
        "conflict_count":    doc.get("conflict_count", 0),
        "avg_neg_sentiment": doc.get("avg_neg_sentiment", 0.0),
        "top_event_label":   doc.get("top_event_label", "unknown"),
        "sample_title":      doc.get("sample_title", ""),
        "sample_url":        doc.get("sample_url", ""),
    }


def _get_recent_news(db, iso: str, limit: int = 7) -> list[dict]:
    """
    Pull the last N processed events for this country.

    KEY FIX: processed_events stores countries as a nested array:
        { countries: [{iso: "RU", name: "Russia", lat: .., lon: ..}, ...] }
    So we must query with {"countries.iso": iso} not {"iso": iso}.

    Date field is 'published_at' (ISO string), not 'date'.
    """
    docs = list(
        db[settings.COL_PROCESSED_EVENTS]
        .find({"countries.iso": iso.upper()}, {"_id": 0})
        .sort("published_at", -1)
        .limit(limit)
    )
    result = []
    for d in docs:
        text = d.get("title", "")
        result.append({
            "title":       text,
            "url":         d.get("url", ""),
            "source":      d.get("source", ""),
            "date":        d.get("published_at", "")[:10] if d.get("published_at") else "",
            "news_type":   classify_news_type(text),
            "event_label": d.get("event_label", "unknown"),
        })
    return result


def _generate_prediction(tension: float, news_type: str, label: str) -> dict:
    """
    Heuristic prediction for VIX direction and trade advice.
    Replace with trained LightGBM .predict() call once model is saved.
    """
    if tension >= 0.70:
        vix_prediction = "increase"
        confidence = round(min(0.55 + tension * 0.30, 0.95), 2)
    elif tension >= 0.40:
        vix_prediction = "uncertain"
        confidence = round(min(0.40 + tension * 0.15, 0.95), 2)
    else:
        vix_prediction = "decrease"
        confidence = round(min(0.60 - tension * 0.20, 0.95), 2)

    trade_idea_map = {
        ("increase", "conflict"):     "LONG GLD (gold hedge) + LONG LMT (defence). Avoid local equity ETFs.",
        ("increase", "military"):     "LONG LMT/NOC (defense stocks). Consider PUT options on affected index ETF.",
        ("increase", "sanctions"):    "SHORT country ETF. LONG USD. Watch FX volatility.",
        ("increase", "economic"):     "LONG USO/XOM if oil-related. SHORT growth-sensitive ETFs.",
        ("increase", "diplomatic"):   "WATCH — potential de-escalation. Avoid new short positions.",
        ("increase", "humanitarian"): "LONG GLD. Monitor for commodity disruption.",
        ("decrease", "conflict"):     "LONG local equity ETF on tension relief rally.",
        ("decrease", "diplomatic"):   "LONG local equity ETF. Reduce safe-haven positions.",
        ("uncertain", "other"):       "Stay flat or hedge with GLD until clearer signal.",
    }

    key = (vix_prediction, news_type) if news_type != "other" else ("uncertain", "other")
    trade_idea = trade_idea_map.get(
        key,
        trade_idea_map.get(("uncertain", "other"), "Monitor situation before committing capital.")
    )

    return {
        "vix_direction":     vix_prediction,
        "confidence":        confidence,
        "confidence_pct":    f"{round(confidence * 100)}%",
        "news_type_context": news_type,
        "trade_idea":        trade_idea,
        "risk_level":        "HIGH" if tension >= 0.70 else "MEDIUM" if tension >= 0.40 else "LOW",
    }


@router.get("/{country_iso}")
def get_trading_signals(country_iso: str):
    """
    Full trading analysis for a country:
    - Latest tension data from daily_signals
    - Recent headlines from processed_events (by countries.iso)
    - Stock/ETF signals (LONG / SHORT / WATCH)
    - Prediction + trade idea
    """
    iso = country_iso.upper()
    db  = get_db()

    tension_ctx = _get_latest_tension(db, iso)
    if not tension_ctx:
        raise HTTPException(404, f"No signal data found for country: {iso}. Run pipeline steps 1-3 first.")

    tension_score = tension_ctx["tension_score"]
    recent_news   = _get_recent_news(db, iso)

    # Dominant news type from recent articles
    type_counts: dict[str, int] = {}
    for art in recent_news:
        t = art["news_type"]
        type_counts[t] = type_counts.get(t, 0) + 1
    dominant_type = max(type_counts, key=lambda k: type_counts[k]) if type_counts else "other"

    stock_signals = get_stock_signals(iso, tension_score, dominant_type)
    prediction    = _generate_prediction(tension_score, dominant_type, tension_ctx.get("tension_label", "medium"))

    return {
        "country_iso":        iso,
        "tension":            tension_ctx,
        "dominant_news_type": dominant_type,
        "recent_news":        recent_news,
        "stock_signals":      stock_signals,
        "prediction":         prediction,
    }
