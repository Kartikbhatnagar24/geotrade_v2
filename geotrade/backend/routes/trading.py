"""
backend/routes/trading.py
──────────────────────────
GET /trading/{country_iso}

Returns a full trading intelligence package for a country:
  - tension context (latest daily signal)
  - recent news with sentiment + intensity fields
  - stock/ETF signals (LONG / SHORT / WATCH)
  - prediction: VIX direction, tension momentum, market signals,
                key risks, positioning summary
"""

from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, HTTPException
from backend.core.database import get_db
from config.settings import settings
from pipeline.scoring.stocks import get_stock_signals
from pipeline.modeling.predictor import predict_for_country, get_meta as get_predictor_meta

router = APIRouter(prefix="/trading", tags=["Trading"])

# A signal older than this is flagged as stale to the UI rather than passed off
# as "current". 7 days lines up with the GDELT ingestion window.
_TENSION_STALE_DAYS = 7
# Recent-news lookback — must agree with the ingestion retention window (2× INGESTION_DAYS_BACK).
_RECENT_NEWS_LOOKBACK_DAYS = max(settings.INGESTION_DAYS_BACK, 14) * 2


def _age_in_days(date_str: str) -> int | None:
    """Days between today (UTC) and a YYYY-MM-DD string. None if unparseable."""
    if not date_str:
        return None
    try:
        d = datetime.strptime(date_str[:10], "%Y-%m-%d").replace(tzinfo=timezone.utc)
    except ValueError:
        return None
    return (datetime.now(timezone.utc) - d).days


# ── DB helpers ────────────────────────────────────────────────────────────────

def _get_latest_tension(db, iso: str) -> dict:
    doc = db[settings.COL_DAILY_SIGNALS].find_one(
        {"iso": iso.upper()}, sort=[("date", -1)]
    )
    if not doc:
        return {}
    date     = doc.get("date", "")
    age_days = _age_in_days(date)
    return {
        "tension_score":     doc.get("tension_score", 0.5),
        "smoothed_score":    doc.get("smoothed_score", doc.get("tension_score", 0.5)),
        "tension_label":     doc.get("tension_label", "medium"),
        "date":              date,
        "age_days":          age_days,
        "is_stale":          age_days is not None and age_days > _TENSION_STALE_DAYS,
        "event_count":       doc.get("event_count", 0),
        "conflict_gravity":  doc.get("conflict_gravity", 0.0),
        "coverage_signal":   doc.get("coverage_signal", 0.0),
        "avg_neg_sentiment": doc.get("avg_neg_sentiment", 0.0),
        "top_event_label":   doc.get("top_event_label", "unknown"),
        "sample_title":      doc.get("sample_title", ""),
        "sample_url":        doc.get("sample_url", ""),
    }


def _get_recent_news(db, iso: str, limit: int = 8) -> list[dict]:
    """Pull last N processed events within the live ingestion window."""
    cutoff = (datetime.now(timezone.utc)
              - timedelta(days=_RECENT_NEWS_LOOKBACK_DAYS)).isoformat()
    docs = list(
        db[settings.COL_PROCESSED_EVENTS]
        .find(
            {
                "countries.iso": iso.upper(),
                "published_at":  {"$gte": cutoff},
            },
            {"_id": 0},
        )
        .sort("published_at", -1)
        .limit(limit)
    )
    result = []
    for d in docs:
        text          = d.get("title", "")
        sent_label    = d.get("sentiment_label", "NEUTRAL")
        sent_score    = d.get("sentiment_score", 0.5)
        intensity     = d.get("intensity_score", 0.0)
        result.append({
            "title":           text,
            "url":             d.get("url", ""),
            "source":          d.get("source", ""),
            "date":            d.get("published_at", "")[:10] if d.get("published_at") else "",
            "news_type":       d.get("event_label", "other"),
            "event_label":     d.get("event_label", "unknown"),
            "sentiment_label": sent_label,
            "sentiment_score": round(sent_score, 3),
            "intensity_score": round(intensity, 3),
        })
    return result


def _compute_tension_momentum(db, iso: str) -> dict:
    """
    Fetch last 7 days of tension history and compute momentum metrics:
      change_3d    : tension change over last 3 days
      change_7d    : tension change over last 7 days
      acceleration : whether tension is speeding up, steady, or slowing
      signal_strength : strong / moderate / weak based on magnitude
    """
    docs = list(
        db[settings.COL_DAILY_SIGNALS]
        .find({"iso": iso.upper()},
              {"date": 1, "tension_score": 1, "_id": 0})
        .sort("date", -1)
        .limit(7)
    )
    if len(docs) < 2:
        return {
            "change_3d": 0.0, "change_7d": 0.0,
            "acceleration": "steady", "signal_strength": "weak",
            "scores": [], "dates": [],
        }

    # Chronological order
    docs   = list(reversed(docs))
    scores = [d["tension_score"] for d in docs]
    dates  = [d["date"] for d in docs]
    n      = len(scores)
    current = scores[-1]

    change_3d = round(current - scores[max(0, n - 4)], 3)
    change_7d = round(current - scores[0], 3)

    # Acceleration: slope of second half vs first half
    if n >= 4:
        mid               = n // 2
        slope_first_half  = (scores[mid] - scores[0]) / max(mid, 1)
        slope_second_half = (scores[-1] - scores[mid]) / max(n - mid, 1)
        accel_delta       = slope_second_half - slope_first_half
        acceleration      = "rising" if accel_delta > 0.015 else \
                            "falling" if accel_delta < -0.015 else "steady"
    else:
        acceleration = "rising" if change_7d > 0.05 else \
                       "falling" if change_7d < -0.05 else "steady"

    abs_change      = abs(change_7d)
    signal_strength = "strong" if abs_change >= 0.2 else \
                      "moderate" if abs_change >= 0.08 else "weak"

    return {
        "change_3d":      change_3d,
        "change_7d":      change_7d,
        "acceleration":   acceleration,
        "signal_strength": signal_strength,
        "scores":         [round(s, 3) for s in scores],
        "dates":          dates,
    }


# ── Market signal engine ──────────────────────────────────────────────────────

# Countries where energy (oil/gas) is a primary geopolitical lever
_ENERGY_ISOS = {"IR", "IQ", "SA", "YE", "LY", "NG", "AZ", "RU", "VE", "KW", "QA", "AE", "LB", "SY"}

# Countries with significant semiconductor / tech supply chain relevance
_TECH_ISOS = {"TW", "KR", "CN", "JP", "MY", "SG", "VN"}

# Countries where grain / commodity is a primary disruption vector
_GRAIN_ISOS = {"UA", "RU", "SD", "ET", "ML", "TD", "EG"}


def _generate_market_signals(iso: str, tension: float, news_type: str,
                              momentum: dict) -> list[dict]:
    """
    Generate 4-6 asset-class market signals with conviction scores (1-5 stars).
    Each signal is specific to this country's geopolitical context.
    """
    signals   = []
    is_high   = tension >= 0.65
    is_medium = 0.35 <= tension < 0.65
    accel     = momentum.get("acceleration", "steady")
    chg7d     = momentum.get("change_7d", 0.0)

    # ── Safe Havens ───────────────────────────────────────────
    if is_high:
        conviction = 5 if accel == "rising" else 4
        signals.append({
            "asset_class": "Safe Havens",
            "tickers":     ["GLD", "TLT", "CHF"],
            "direction":   "LONG",
            "conviction":  conviction,
            "rationale":   f"{'Accelerating' if accel == 'rising' else 'Elevated'} {news_type} activity drives flight-to-safety. Gold and Treasury demand expected to rise.",
        })
    elif is_medium and accel == "rising":
        signals.append({
            "asset_class": "Safe Havens",
            "tickers":     ["GLD"],
            "direction":   "WATCH",
            "conviction":  3,
            "rationale":   "Tension rising toward high zone — begin building gold hedge position on any dip.",
        })
    else:
        signals.append({
            "asset_class": "Safe Havens",
            "tickers":     ["GLD"],
            "direction":   "SHORT" if chg7d < -0.1 else "WATCH",
            "conviction":  2,
            "rationale":   "Tension subdued — safe-haven premium compressing. Reduce gold allocation if de-escalation continues.",
        })

    # ── Energy / Oil ──────────────────────────────────────────
    if iso in _ENERGY_ISOS:
        if news_type in ("conflict", "military", "sanctions") and is_high:
            signals.append({
                "asset_class": "Energy / Oil",
                "tickers":     ["USO", "XOM", "XLE"],
                "direction":   "LONG",
                "conviction":  4 if news_type == "sanctions" else 5,
                "rationale":   f"{'Sanctions on an oil producer' if news_type == 'sanctions' else 'Active conflict'} threatens regional supply routes. Brent crude upside risk is high.",
            })
        else:
            signals.append({
                "asset_class": "Energy / Oil",
                "tickers":     ["USO"],
                "direction":   "WATCH",
                "conviction":  3,
                "rationale":   "Energy-producing region with moderate risk. Geopolitical premium remains — hold current exposure.",
            })

    # ── Defense & Aerospace ───────────────────────────────────
    if news_type in ("conflict", "military") and tension >= 0.45:
        conv = 5 if tension >= 0.7 else 4 if tension >= 0.55 else 3
        signals.append({
            "asset_class": "Defense & Aerospace",
            "tickers":     ["LMT", "NOC", "RTX", "BA"],
            "direction":   "LONG",
            "conviction":  conv,
            "rationale":   f"{'Active conflict' if news_type == 'conflict' else 'Military escalation'} drives defense procurement expectations and NATO spending commitments.",
        })

    # ── Semiconductors / Tech ─────────────────────────────────
    if iso in _TECH_ISOS:
        if news_type in ("conflict", "sanctions", "military") and is_high:
            signals.append({
                "asset_class": "Semiconductors / Tech",
                "tickers":     ["SMH", "SOXX"],
                "direction":   "SHORT",
                "conviction":  4,
                "rationale":   f"{'Taiwan Strait risk' if iso == 'TW' else iso + ' tech conflict'} threatens global chip supply chain. Semiconductor ETFs face downside risk.",
            })
        elif iso == "TW" and is_medium:
            signals.append({
                "asset_class": "Semiconductors / Tech",
                "tickers":     ["SMH"],
                "direction":   "WATCH",
                "conviction":  3,
                "rationale":   "Taiwan risk keeps semiconductor sector on edge — hedge exposure, do not add.",
            })

    # ── Agriculture / Commodities ─────────────────────────────
    if iso in _GRAIN_ISOS and news_type in ("conflict", "humanitarian", "sanctions") and tension >= 0.5:
        signals.append({
            "asset_class": "Agriculture",
            "tickers":     ["WEAT", "CORN", "DBA"],
            "direction":   "LONG",
            "conviction":  3,
            "rationale":   f"Conflict in a major grain-producing region disrupts food supply chains. Wheat and corn futures face supply-side squeeze.",
        })

    # ── Local Equity ──────────────────────────────────────────
    if is_high and news_type in ("conflict", "sanctions", "military"):
        signals.append({
            "asset_class": "Local Equity",
            "tickers":     ["Country ETF"],
            "direction":   "SHORT",
            "conviction":  4 if news_type == "conflict" else 3,
            "rationale":   f"{'Active conflict' if news_type == 'conflict' else 'Sanctions'} creates capital flight risk from domestic markets. Short or avoid local equity ETF.",
        })
    elif not is_high and accel == "falling":
        signals.append({
            "asset_class": "Local Equity",
            "tickers":     ["Country ETF"],
            "direction":   "LONG",
            "conviction":  3,
            "rationale":   "Tension de-escalating — domestic equity likely to see relief rally as risk premium unwinds.",
        })
    else:
        signals.append({
            "asset_class": "Local Equity",
            "tickers":     ["Country ETF"],
            "direction":   "WATCH",
            "conviction":  2,
            "rationale":   "Mixed signals — wait for clearer trend before committing to domestic equity position.",
        })

    # ── FX / Currencies ───────────────────────────────────────
    if news_type == "sanctions" and is_high:
        signals.append({
            "asset_class": "FX / Currencies",
            "tickers":     ["UUP", "FXF"],
            "direction":   "LONG",
            "conviction":  3,
            "rationale":   "Sanctions typically trigger rapid local currency devaluation. LONG USD and CHF as safe-haven FX versus emerging market exposure.",
        })

    # Sort by conviction descending
    signals.sort(key=lambda s: (-s["conviction"], s["direction"]))
    return signals[:6]  # cap at 6 signals


# ── Key risks ────────────────────────────────────────────────────────────────

_RISK_BANK: dict[str, list[str]] = {
    "conflict":     [
        "Escalation to full-scale military confrontation",
        "Civilian infrastructure targeting triggering international intervention",
        "Regional spillover drawing in neighboring powers",
    ],
    "military":     [
        "Nuclear or advanced weapons deployment crossing red lines",
        "Alliance activation clause (NATO Art. 5) triggered",
        "Critical infrastructure (energy grid, ports) struck",
    ],
    "sanctions":    [
        "Retaliatory sanctions broadening to new commodity classes",
        "Secondary sanctions pressuring third-country trading partners",
        "Debt default or banking system freeze",
    ],
    "diplomatic":   [
        "Talks collapse triggering rapid escalation cycle",
        "Third-party spoiler (non-state actor) derailing negotiations",
        "Agreement signed but implementation fails",
    ],
    "economic":     [
        "Currency crisis and capital flight",
        "Supply chain disruption cascading to global markets",
        "Sovereign default and contagion to EM peers",
    ],
    "humanitarian": [
        "Famine or disease outbreak destabilizing government",
        "Refugee flows destabilizing neighboring countries",
        "Aid delivery blocked escalating international pressure",
    ],
    "elections":    [
        "Result disputed triggering political violence",
        "Military intervention nullifying election outcome",
        "New government reversing key international agreements",
    ],
}

_GENERIC_RISKS = [
    "Unexpected black swan event accelerating current trajectory",
    "Market overreaction creating liquidity crunch",
    "Information asymmetry — ground reality worse than reported",
]


def _get_key_risks(news_type: str, tension: float, iso: str) -> list[str]:
    base   = _RISK_BANK.get(news_type, _RISK_BANK["conflict"])[:2]
    extras = _GENERIC_RISKS[:1] if tension >= 0.6 else []
    # Energy-specific risk
    if iso in _ENERGY_ISOS and news_type in ("conflict", "sanctions", "military"):
        base.insert(1, "Oil supply route disruption spiking Brent crude above $100")
    return (base + extras)[:3]


def _positioning_summary(tension: float, vix_dir: str, momentum: dict) -> str:
    accel = momentum.get("acceleration", "steady")
    if vix_dir == "increase" and tension >= 0.7:
        prefix = "DEFENSIVE"
        detail = "max safe-haven allocation, exit local equity, reduce duration risk"
    elif vix_dir == "increase" and accel == "rising":
        prefix = "CAUTIOUS"
        detail = "add safe-haven hedge, trim EM exposure, hold cash buffer"
    elif vix_dir == "decrease" and accel == "falling":
        prefix = "CONSTRUCTIVE"
        detail = "add local equity on dip, reduce gold allocation, re-enter cyclicals"
    elif vix_dir == "uncertain":
        prefix = "NEUTRAL"
        detail = "balanced positioning, await clearer directional signal before adding risk"
    else:
        prefix = "SELECTIVE"
        detail = "tactical safe-haven hedge, avoid binary bets on direction"
    return f"{prefix} — {detail}"


# ── ML prediction ────────────────────────────────────────────────────────────

def _ml_prediction(db, iso: str) -> dict:
    return predict_for_country(iso)


# ── Heuristic fallback ────────────────────────────────────────────────────────

_TRADE_IDEAS: dict[tuple, str] = {
    ("increase", "conflict"):     "LONG GLD + LONG LMT. Avoid local equity ETFs.",
    ("increase", "military"):     "LONG LMT/NOC. Consider PUT options on affected index ETF.",
    ("increase", "sanctions"):    "SHORT country ETF. LONG USD. Watch FX volatility.",
    ("increase", "economic"):     "LONG USO/XOM if oil-related. SHORT growth-sensitive ETFs.",
    ("increase", "diplomatic"):   "WATCH — potential de-escalation. Avoid new shorts.",
    ("increase", "humanitarian"): "LONG GLD. Monitor for commodity disruption.",
    ("decrease", "conflict"):     "LONG local equity ETF on tension relief rally.",
    ("decrease", "diplomatic"):   "LONG local equity ETF. Reduce safe-haven positions.",
    ("uncertain", "other"):       "Stay flat or hedge with GLD until clearer signal.",
}


def _generate_prediction(db, tension: float, news_type: str,
                         momentum: dict, iso: str) -> dict:
    # ── Try ML model ──────────────────────────────────────────
    ml_result = _ml_prediction(db, iso)
    if ml_result["used_ml"]:
        # Direction signal (label_up_3d)
        direction      = ml_result.get("direction") or ml_result.get("vix_direction")
        direction_prob = ml_result.get("direction_prob") or ml_result.get("probability")
        direction_pct  = ml_result.get("direction_pct") or ml_result.get("confidence_pct")
        direction_auc  = ml_result.get("direction_auc")
        # Volatility signal (label_vol_high_5d)
        vol_level      = ml_result.get("vol_level")
        vol_prob       = ml_result.get("vol_prob")
        vol_pct        = ml_result.get("vol_pct")
        vol_auc        = ml_result.get("vol_auc")
        # Risk driven by vol model when available, else tension
        risk_level     = ml_result.get("risk_level") or (
            "HIGH" if tension >= 0.70 else "MEDIUM" if tension >= 0.40 else "LOW"
        )
        no_data_reason = ""
        model_source   = "ml-ensemble"
    else:
        no_data_reason = ml_result.get("no_data_reason", "")
        model_source   = "rule-based"
        vol_level = vol_prob = vol_pct = vol_auc = None
        direction_auc = None

        accel = momentum.get("acceleration", "steady")
        chg7d = momentum.get("change_7d", 0.0)
        chg3d = momentum.get("change_3d", 0.0)

        # High tension, or medium tension that is actively rising -> VIX likely up
        if tension >= 0.65 or (tension >= 0.50 and accel == "rising"):
            direction      = "increase"
            direction_prob = round(min(0.56 + tension * 0.25, 0.92), 2)
        # Low tension, or medium tension that is actively falling -> VIX likely down
        elif tension < 0.30 or (tension < 0.45 and accel == "falling"):
            direction      = "decrease"
            direction_prob = round(max(0.60 - tension * 0.30, 0.55), 2)
        # Middle band: use recent momentum to break the tie
        elif chg3d > 0.04 or chg7d > 0.07:
            direction      = "increase"
            direction_prob = round(min(0.54 + abs(chg7d) * 0.30, 0.82), 2)
        elif chg3d < -0.04 or chg7d < -0.07:
            direction      = "decrease"
            direction_prob = round(min(0.54 + abs(chg7d) * 0.30, 0.82), 2)
        # Only truly flat situations get "uncertain"
        else:
            direction      = "uncertain"
            direction_prob = 0.50

        direction_pct  = f"{round(direction_prob * 100)}%"
        risk_level     = "HIGH" if tension >= 0.70 else "MEDIUM" if tension >= 0.40 else "LOW"

    market_signals = _generate_market_signals(iso, tension, news_type, momentum)
    key_risks      = _get_key_risks(news_type, tension, iso)
    pos_summary    = _positioning_summary(tension, direction, momentum)

    return {
        # Direction signal
        "direction":      direction,
        "direction_prob": direction_prob,
        "direction_pct":  direction_pct,
        "direction_auc":  direction_auc,
        # Volatility signal
        "vol_level":      vol_level,
        "vol_prob":       vol_prob,
        "vol_pct":        vol_pct,
        "vol_auc":        vol_auc,
        # Combined
        "risk_level":         risk_level,
        "news_type_context":  news_type,
        "model_source":       model_source,
        "no_data_reason":     no_data_reason,
        "tension_momentum":   momentum,
        "market_signals":     market_signals,
        "key_risks":          key_risks,
        "positioning_summary": pos_summary,
        # Legacy aliases kept for backward compat
        "vix_direction":  direction,
        "confidence":     direction_prob,
        "confidence_pct": direction_pct,
    }


# ── Route ────────────────────────────────────────────────────────────────────

@router.get("/{country_iso}")
def get_trading_signals(country_iso: str):
    iso = country_iso.upper()
    db  = get_db()

    tension_ctx = _get_latest_tension(db, iso)
    if not tension_ctx:
        raise HTTPException(404, f"No signal data for '{iso}'. Run pipeline steps 1-3 first.")

    tension_score = tension_ctx["tension_score"]
    recent_news   = _get_recent_news(db, iso)
    momentum      = _compute_tension_momentum(db, iso)

    # Dominant news type from recent headlines
    type_counts: dict[str, int] = {}
    for art in recent_news:
        t = art["news_type"]
        type_counts[t] = type_counts.get(t, 0) + 1
    dominant_type = max(type_counts, key=lambda k: type_counts[k]) if type_counts else "other"

    stock_signals = get_stock_signals(iso, tension_score, dominant_type)
    prediction    = _generate_prediction(
        db        = db,
        tension   = tension_score,
        news_type = dominant_type,
        momentum  = momentum,
        iso       = iso,
    )

    return {
        "country_iso":        iso,
        "tension":            tension_ctx,
        "dominant_news_type": dominant_type,
        "recent_news":        recent_news,
        "stock_signals":      stock_signals,
        "prediction":         prediction,
    }
