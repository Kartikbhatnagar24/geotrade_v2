"""
pipeline/scoring/stocks.py
───────────────────────────
Index-relative signal engine.

Maps country ISO → (local market index, safe-haven, sector proxy)
and returns trade signals based on:
    signal_strength = tension_score × regime_multiplier × news_type_weight

Tiers:
  Tier 1 — own liquid index available on yfinance  (^GSPC, ^BSESN, etc.)
  Tier 2 — country ETF available                   (INDA, EIS, EWZ, etc.)
  Tier 3 — conflict zone / no liquid instrument    (fallback: GLD / EEM / USO)

Direction rules:
  HIGH   (strength >= 0.65) -> local SHORT, safe_haven LONG, sector depends on type
  MEDIUM (strength >= 0.35) -> all WATCH
  LOW    (strength < 0.35)  -> local LONG (relief rally), safe_haven REDUCE
"""

from __future__ import annotations

import json
import time
from pathlib import Path
import pandas as pd
import yfinance as yf

# 5-minute in-memory cache for yfinance results — keyed by ticker.
# Each entry: {"value": dict, "ts": float epoch seconds}
_PRICE_CACHE: dict[str, dict] = {}
_PRICE_TTL_SECONDS: float = 300.0

_DATA = json.loads(
    (Path(__file__).resolve().parent.parent.parent.parent / "data" / "indexes.json").read_text()
)
INDEX_MAP: dict[str, dict] = {
    iso: {**entry, "local_index": tuple(entry["local_index"])}
    for iso, entry in _DATA["countries"].items()
}
_DEFAULT_ENTRY: dict = {**_DATA["default"], "local_index": tuple(_DATA["default"]["local_index"])}
_NAMES: dict[str, str] = _DATA["names"]


# ── Regime multiplier ─────────────────────────────────────────
_REGIME_MULT: dict[str, float] = {
    "CALM":     0.5,
    "RISING":   0.8,
    "STRESSED": 1.0,
    "CRISIS":   1.2,
}

# ── News-type weight ──────────────────────────────────────────
_NEWS_WEIGHT: dict[str, float] = {
    "military":     1.2,
    "conflict":     1.1,
    "sanctions":    1.0,
    "economic":     0.9,
    "diplomatic":   0.6,
    "humanitarian": 0.7,
    "other":        0.5,
}


# ── Price fetcher ─────────────────────────────────────────────

def _fetch_price(ticker: str, retries: int = 2) -> dict:
    now = time.time()
    cached = _PRICE_CACHE.get(ticker)
    if cached and (now - cached["ts"]) < _PRICE_TTL_SECONDS:
        return cached["value"]

    for attempt in range(retries + 1):
        try:
            df = yf.download(
                ticker,
                period="5d",
                progress=False,
                auto_adjust=True,
            )
            if df.empty:
                if attempt < retries:
                    time.sleep(1.5)
                    continue
                result = {"price": None, "change_5d": None, "error": "no data"}
                _PRICE_CACHE[ticker] = {"value": result, "ts": now}
                return result
            if isinstance(df.columns, pd.MultiIndex):
                df.columns = df.columns.get_level_values(0)
            close = df["Close"].dropna()
            if len(close) == 0:
                result = {"price": None, "change_5d": None, "error": "no close data"}
                _PRICE_CACHE[ticker] = {"value": result, "ts": now}
                return result
            latest = float(close.iloc[-1])
            prev   = float(close.iloc[0])
            change = round((latest - prev) / prev * 100, 2) if prev != 0 else None
            result = {"price": round(latest, 2), "change_5d": change}
            _PRICE_CACHE[ticker] = {"value": result, "ts": now}
            return result
        except Exception as e:
            if attempt < retries:
                time.sleep(1.5)
                continue
            return {"price": None, "change_5d": None, "error": str(e)[:80]}
    return {"price": None, "change_5d": None, "error": "max retries exceeded"}


def _fetch_index_context(display_ticker: str | None) -> dict:
    if not display_ticker:
        return {}
    data = _fetch_price(display_ticker)
    return {
        "index_ticker":    display_ticker,
        "index_price":     data.get("price"),
        "index_change_5d": data.get("change_5d"),
    }


# ── Signal direction ──────────────────────────────────────────

def _compute_signal_strength(tension_score: float, regime: str, news_type: str) -> float:
    mult   = _REGIME_MULT.get(regime, 1.0)
    weight = _NEWS_WEIGHT.get(news_type, 0.5)
    return round(min(tension_score * mult * weight, 1.0), 4)


def _direction_for_local(strength: float, news_type: str) -> str:
    if strength >= 0.65:
        if news_type in ("conflict", "military", "sanctions"):
            return "SHORT"
        return "WATCH"
    if strength >= 0.35:
        return "WATCH"
    return "LONG"


def _direction_for_safe_haven(strength: float) -> str:
    if strength >= 0.65:
        return "LONG"
    if strength >= 0.35:
        return "WATCH"
    return "REDUCE"


def _direction_for_sector(strength: float, news_type: str, sector_proxy: str) -> str:
    if strength < 0.35:
        return "WATCH"
    if strength >= 0.65:
        if sector_proxy == "WEAT":
            return "LONG"
        if sector_proxy in ("USO", "XOM"):
            return "LONG" if news_type in ("conflict", "military") else "WATCH"
        if sector_proxy == "SMH":
            return "SHORT" if news_type == "sanctions" else "WATCH"
        if sector_proxy == "LMT":
            return "LONG"
        return "WATCH"
    return "WATCH"


def _rationale(role: str, direction: str, strength: float, news_type: str, country_iso: str) -> str:
    tension_desc = (
        "High" if strength >= 0.65 else
        "Moderate" if strength >= 0.35 else "Low"
    )
    templates = {
        ("local", "SHORT"):      f"{tension_desc} {news_type} tension in {country_iso} pressures domestic equities.",
        ("local", "LONG"):       f"Easing tensions in {country_iso} support a local equity relief rally.",
        ("local", "WATCH"):      f"Monitor {country_iso} - tension trajectory unclear.",
        ("safe_haven", "LONG"):  "Flight-to-safety demand rises with elevated geopolitical risk.",
        ("safe_haven", "REDUCE"):"Low tension reduces gold/safe-haven premium.",
        ("safe_haven", "WATCH"): "Safe-haven as precautionary hedge; watch for escalation.",
        ("sector", "LONG"):      f"Supply disruption risk from {news_type} event supports this sector.",
        ("sector", "SHORT"):     f"Sanctions / trade restrictions weigh on this sector.",
        ("sector", "WATCH"):     f"Sector sensitive to {news_type} developments; wait for confirmation.",
    }
    return templates.get((role, direction), "Monitor for further developments.")


def _ticker_name(ticker: str) -> str:
    return _NAMES.get(ticker, ticker)


# ── Public API ────────────────────────────────────────────────

def get_stock_signals(
    iso: str,
    tension_score: float,
    news_type: str = "other",
    regime: str = "STRESSED",
    model_confidence: float | None = None,
) -> list[dict]:
    """
    Return index-level trade signals for a country.

    Args:
        iso:              Country ISO-2 code
        tension_score:    0-1 from the scoring pipeline
        news_type:        classifier output
        regime:           market regime (CALM/RISING/STRESSED/CRISIS)
        model_confidence: calibrated P(vol_up_3d) from LightGBM, optional

    Returns:
        List of signal dicts - at most 3 (local, safe_haven, sector)
    """
    iso   = iso.upper()
    entry = INDEX_MAP.get(iso, _DEFAULT_ENTRY)
    tier  = entry["tier"]

    display_ticker, tradeable_etf = entry["local_index"]
    safe_haven_ticker             = entry["safe_haven"]
    sector_ticker                 = entry["sector_proxy"]

    strength = _compute_signal_strength(tension_score, regime, news_type)

    if model_confidence is not None:
        strength = round(0.6 * strength + 0.4 * model_confidence, 4)

    signals: list[dict] = []

    # 1. Local equity index signal
    if tier in (1, 2):
        direction  = _direction_for_local(strength, news_type)
        price_data = _fetch_price(tradeable_etf)
        index_ctx  = _fetch_index_context(display_ticker) if tier == 1 else {}
        signals.append({
            "role":            "local_equity",
            "ticker":          tradeable_etf,
            "name":            _ticker_name(tradeable_etf),
            "direction":       direction,
            "signal_strength": strength,
            "rationale":       _rationale("local", direction, strength, news_type, iso),
            **price_data,
            **index_ctx,
        })
    else:
        signals.append({
            "role":            "local_equity",
            "ticker":          tradeable_etf,
            "name":            _ticker_name(tradeable_etf) + " (EM Proxy)",
            "direction":       _direction_for_local(strength, news_type),
            "signal_strength": strength,
            "rationale":       (
                f"No direct instrument for {iso} equities. "
                f"Using Emerging Market ETF as a regional proxy."
            ),
            **_fetch_price(tradeable_etf),
        })

    # 2. Safe-haven signal
    direction_sh = _direction_for_safe_haven(strength)
    signals.append({
        "role":            "safe_haven",
        "ticker":          safe_haven_ticker,
        "name":            _ticker_name(safe_haven_ticker),
        "direction":       direction_sh,
        "signal_strength": strength,
        "rationale":       _rationale("safe_haven", direction_sh, strength, news_type, iso),
        **_fetch_price(safe_haven_ticker),
    })

    # 3. Sector proxy signal
    direction_sec = _direction_for_sector(strength, news_type, sector_ticker)
    signals.append({
        "role":            "sector_proxy",
        "ticker":          sector_ticker,
        "name":            _ticker_name(sector_ticker),
        "direction":       direction_sec,
        "signal_strength": strength,
        "rationale":       _rationale("sector", direction_sec, strength, news_type, iso),
        **_fetch_price(sector_ticker),
    })

    order = {"LONG": 0, "SHORT": 1, "REDUCE": 2, "WATCH": 3}
    return sorted(signals, key=lambda s: order.get(s["direction"], 4))
