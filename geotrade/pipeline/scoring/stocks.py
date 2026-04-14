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
  HIGH   (strength ≥ 0.65) → local SHORT, safe_haven LONG, sector depends on type
  MEDIUM (strength ≥ 0.35) → all WATCH
  LOW    (strength < 0.35)  → local LONG (relief rally), safe_haven REDUCE
"""

from __future__ import annotations

import pandas as pd
import yfinance as yf
from datetime import datetime, timedelta, timezone


# ── Regime multiplier ─────────────────────────────────────────
_REGIME_MULT: dict[str, float] = {
    "CALM":     0.5,   # geopolitics has less market impact in calm conditions
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

# ── Country ISO → index map ───────────────────────────────────
# Each entry:
#   local_index  : (display_ticker, tradeable_etf)
#                  display_ticker  = raw index (^GSPC etc.) — for context display
#                  tradeable_etf   = liquid ETF you can actually trade
#   safe_haven   : gold / USD proxy ticker
#   sector_proxy : oil / semis / wheat / defence / EM depending on context
#   tier         : 1 = own index, 2 = ETF proxy, 3 = fallback only
INDEX_MAP: dict[str, dict] = {
    # ─── TIER 1 — own liquid index ────────────────────────────
    "US": {
        "local_index":  ("^GSPC",   "SPY"),
        "safe_haven":   "GLD",
        "sector_proxy": "LMT",       # defence — US events → defence relevant
        "tier": 1,
    },
    "IN": {
        "local_index":  ("^BSESN",  "INDA"),
        "safe_haven":   "GLD",
        "sector_proxy": "USO",
        "tier": 1,
    },
    "CN": {
        "local_index":  ("000001.SS", "FXI"),
        "safe_haven":   "GLD",
        "sector_proxy": "SMH",       # semiconductor ETF — Taiwan Strait / chip wars
        "tier": 1,
    },
    "JP": {
        "local_index":  ("^N225",   "EWJ"),
        "safe_haven":   "GLD",
        "sector_proxy": "SMH",
        "tier": 1,
    },
    "GB": {
        "local_index":  ("^FTSE",   "EWU"),
        "safe_haven":   "GLD",
        "sector_proxy": "USO",
        "tier": 1,
    },
    "DE": {
        "local_index":  ("^GDAXI",  "EWG"),
        "safe_haven":   "GLD",
        "sector_proxy": "USO",
        "tier": 1,
    },
    "FR": {
        "local_index":  ("^FCHI",   "EWQ"),
        "safe_haven":   "GLD",
        "sector_proxy": "USO",
        "tier": 1,
    },
    "KR": {
        "local_index":  ("^KS11",   "EWY"),
        "safe_haven":   "GLD",
        "sector_proxy": "SMH",       # Korea = memory chip hub
        "tier": 1,
    },
    "TW": {
        "local_index":  ("^TWII",   "EWT"),
        "safe_haven":   "GLD",
        "sector_proxy": "SMH",       # Taiwan = semiconductor capital
        "tier": 1,
    },
    "BR": {
        "local_index":  ("^BVSP",   "EWZ"),
        "safe_haven":   "GLD",
        "sector_proxy": "USO",
        "tier": 1,
    },
    "MX": {
        "local_index":  ("^MXX",    "EWW"),
        "safe_haven":   "GLD",
        "sector_proxy": "USO",
        "tier": 1,
    },
    # ─── TIER 2 — country ETF proxy ───────────────────────────
    "IL": {
        "local_index":  ("^TA125.TA", "EIS"),
        "safe_haven":   "GLD",
        "sector_proxy": "USO",       # Middle East → oil
        "tier": 2,
    },
    "SA": {
        "local_index":  ("^TASI.SR", "KSA"),
        "safe_haven":   "GLD",
        "sector_proxy": "USO",
        "tier": 2,
    },
    "TR": {
        "local_index":  ("XU100.IS", "TUR"),
        "safe_haven":   "GLD",
        "sector_proxy": "USO",
        "tier": 2,
    },
    "PK": {
        "local_index":  ("^KSE100",  "INDA"),  # use INDA as closest tradeable proxy
        "safe_haven":   "GLD",
        "sector_proxy": "USO",
        "tier": 2,
    },
    "PL": {
        "local_index":  ("^WIG20",   "EPOL"),
        "safe_haven":   "GLD",
        "sector_proxy": "EEM",
        "tier": 2,
    },
    "GR": {
        "local_index":  ("^ATG",     "GREK"),
        "safe_haven":   "GLD",
        "sector_proxy": "EEM",
        "tier": 2,
    },
    "EG": {
        "local_index":  ("^CASE30",  "EGPT"),
        "safe_haven":   "GLD",
        "sector_proxy": "USO",
        "tier": 2,
    },
    "ZA": {
        "local_index":  ("^J203.JO", "EZA"),
        "safe_haven":   "GLD",
        "sector_proxy": "EEM",
        "tier": 2,
    },
    "AR": {
        "local_index":  ("^MERV",    "ARGT"),
        "safe_haven":   "GLD",
        "sector_proxy": "EEM",
        "tier": 2,
    },
    "CO": {
        "local_index":  ("^COLCAP",  "GXG"),
        "safe_haven":   "GLD",
        "sector_proxy": "USO",
        "tier": 2,
    },
    "ID": {
        "local_index":  ("^JKSE",    "EIDO"),
        "safe_haven":   "GLD",
        "sector_proxy": "USO",
        "tier": 2,
    },
    "PH": {
        "local_index":  ("^PSI",     "EPHE"),
        "safe_haven":   "GLD",
        "sector_proxy": "EEM",
        "tier": 2,
    },
    "SE": {
        "local_index":  ("^OMX",     "EWD"),
        "safe_haven":   "GLD",
        "sector_proxy": "EEM",
        "tier": 2,
    },
    "FI": {
        "local_index":  ("^OMXH25",  "EWQ"),  # use EWQ France ETF as Nordic proxy
        "safe_haven":   "GLD",
        "sector_proxy": "EEM",
        "tier": 2,
    },
    # ─── TIER 3 — conflict zones / no liquid instrument ───────
    # LOCAL is not tradeable → only safe_haven + sector_proxy signalled
    "RU": {
        "local_index":  (None,        "EEM"),   # MOEX sanctioned; EEM as EM proxy
        "safe_haven":   "GLD",
        "sector_proxy": "USO",        # Russia = major oil producer
        "tier": 3,
    },
    "UA": {
        "local_index":  (None,        "EEM"),
        "safe_haven":   "GLD",
        "sector_proxy": "WEAT",       # Ukraine = wheat breadbasket
        "tier": 3,
    },
    "IR": {
        "local_index":  (None,        "EEM"),
        "safe_haven":   "GLD",
        "sector_proxy": "USO",        # Iran = major oil producer
        "tier": 3,
    },
    "IQ": {
        "local_index":  (None,        "USO"),
        "safe_haven":   "GLD",
        "sector_proxy": "USO",
        "tier": 3,
    },
    "SY": {
        "local_index":  (None,        "EEM"),
        "safe_haven":   "GLD",
        "sector_proxy": "USO",
        "tier": 3,
    },
    "YE": {
        "local_index":  (None,        "USO"),   # Houthi / Red Sea → oil / shipping
        "safe_haven":   "GLD",
        "sector_proxy": "USO",
        "tier": 3,
    },
    "AF": {
        "local_index":  (None,        "GLD"),
        "safe_haven":   "GLD",
        "sector_proxy": "GLD",
        "tier": 3,
    },
    "MM": {
        "local_index":  (None,        "EEM"),
        "safe_haven":   "GLD",
        "sector_proxy": "EEM",
        "tier": 3,
    },
    "SD": {
        "local_index":  (None,        "EEM"),
        "safe_haven":   "GLD",
        "sector_proxy": "EEM",
        "tier": 3,
    },
    "NG": {
        "local_index":  (None,        "EEM"),
        "safe_haven":   "GLD",
        "sector_proxy": "USO",
        "tier": 3,
    },
    "LB": {
        "local_index":  (None,        "EEM"),
        "safe_haven":   "GLD",
        "sector_proxy": "USO",
        "tier": 3,
    },
    "KP": {
        "local_index":  (None,        "EWY"),   # N.Korea → signal via S.Korea ETF
        "safe_haven":   "GLD",
        "sector_proxy": "SMH",
        "tier": 3,
    },
    "VE": {
        "local_index":  (None,        "EEM"),
        "safe_haven":   "GLD",
        "sector_proxy": "USO",
        "tier": 3,
    },
    "BY": {
        "local_index":  (None,        "EEM"),
        "safe_haven":   "GLD",
        "sector_proxy": "EEM",
        "tier": 3,
    },
    "AZ": {
        "local_index":  (None,        "EEM"),
        "safe_haven":   "GLD",
        "sector_proxy": "USO",
        "tier": 3,
    },
    "AM": {
        "local_index":  (None,        "EEM"),
        "safe_haven":   "GLD",
        "sector_proxy": "EEM",
        "tier": 3,
    },
    "ML": {
        "local_index":  (None,        "EEM"),
        "safe_haven":   "GLD",
        "sector_proxy": "EEM",
        "tier": 3,
    },
    "CD": {
        "local_index":  (None,        "EEM"),
        "safe_haven":   "GLD",
        "sector_proxy": "EEM",
        "tier": 3,
    },
    "HT": {
        "local_index":  (None,        "EEM"),
        "safe_haven":   "GLD",
        "sector_proxy": "EEM",
        "tier": 3,
    },
    "PS": {
        "local_index":  (None,        "EEM"),
        "safe_haven":   "GLD",
        "sector_proxy": "USO",
        "tier": 3,
    },
    "LY": {
        "local_index":  (None,        "EEM"),
        "safe_haven":   "GLD",
        "sector_proxy": "USO",
        "tier": 3,
    },
    "SO": {
        "local_index":  (None,        "EEM"),
        "safe_haven":   "GLD",
        "sector_proxy": "EEM",
        "tier": 3,
    },
    "ET": {
        "local_index":  (None,        "EEM"),
        "safe_haven":   "GLD",
        "sector_proxy": "EEM",
        "tier": 3,
    },
}

# Fallback for any unlisted country
_DEFAULT_ENTRY: dict = {
    "local_index":  (None, "EEM"),
    "safe_haven":   "GLD",
    "sector_proxy": "USO",
    "tier": 3,
}


# ── Price fetcher ─────────────────────────────────────────────

def _fetch_price(ticker: str, retries: int = 2) -> dict:
    """
    Fetch current price + 5-day change from yfinance.
    Uses period='5d' (more reliable than explicit date ranges on yfinance).
    Retries up to `retries` times on empty-data failures.
    """
    import time
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
                return {"price": None, "change_5d": None, "error": "no data"}
            # Flatten MultiIndex columns if present
            if isinstance(df.columns, pd.MultiIndex):
                df.columns = df.columns.get_level_values(0)
            close = df["Close"].dropna()
            if len(close) == 0:
                return {"price": None, "change_5d": None, "error": "no close data"}
            latest  = float(close.iloc[-1])
            prev    = float(close.iloc[0])
            change  = round((latest - prev) / prev * 100, 2) if prev != 0 else None
            return {"price": round(latest, 2), "change_5d": change}
        except Exception as e:
            if attempt < retries:
                time.sleep(1.5)
                continue
            return {"price": None, "change_5d": None, "error": str(e)[:80]}
    return {"price": None, "change_5d": None, "error": "max retries exceeded"}


def _fetch_index_context(display_ticker: str | None) -> dict:
    """Fetch native index level for contextual display (non-tradeable)."""
    if not display_ticker:
        return {}
    data = _fetch_price(display_ticker)
    return {
        "index_ticker":     display_ticker,
        "index_price":      data.get("price"),
        "index_change_5d":  data.get("change_5d"),
    }


# ── Signal direction ──────────────────────────────────────────

def _compute_signal_strength(
    tension_score: float,
    regime: str,
    news_type: str,
) -> float:
    """Combine tension, regime, and news-type into a single 0–1 signal strength."""
    mult   = _REGIME_MULT.get(regime, 1.0)
    weight = _NEWS_WEIGHT.get(news_type, 0.5)
    return round(min(tension_score * mult * weight, 1.0), 4)


def _direction_for_local(strength: float, news_type: str) -> str:
    if strength >= 0.65:
        # Conflict/military/sanctions → equity pressure DOWN
        if news_type in ("conflict", "military", "sanctions"):
            return "SHORT"
        # Diplomatic — ambiguous, don't short
        return "WATCH"
    if strength >= 0.35:
        return "WATCH"
    # Low tension → relief rally
    return "LONG"


def _direction_for_safe_haven(strength: float) -> str:
    if strength >= 0.65:
        return "LONG"
    if strength >= 0.35:
        return "WATCH"
    return "REDUCE"   # de-risk safe-haven position in calm environment


def _direction_for_sector(strength: float, news_type: str, sector_proxy: str) -> str:
    if strength < 0.35:
        return "WATCH"
    if strength >= 0.65:
        if sector_proxy == "WEAT":
            return "LONG"   # conflict disrupts wheat supply
        if sector_proxy in ("USO", "XOM"):
            return "LONG" if news_type in ("conflict", "military") else "WATCH"
        if sector_proxy == "SMH":
            # Semiconductors: SHORT on China tension (supply chain), LONG otherwise
            return "SHORT" if news_type == "sanctions" else "WATCH"
        if sector_proxy == "LMT":
            return "LONG"   # defence always benefits from escalation
        return "WATCH"
    return "WATCH"


def _rationale(role: str, direction: str, strength: float, news_type: str, country_iso: str) -> str:
    """Generate a human-readable rationale string."""
    tension_desc = (
        "High" if strength >= 0.65 else
        "Moderate" if strength >= 0.35 else "Low"
    )
    templates = {
        ("local", "SHORT"):  f"{tension_desc} {news_type} tension in {country_iso} pressures domestic equities.",
        ("local", "LONG"):   f"Easing tensions in {country_iso} support a local equity relief rally.",
        ("local", "WATCH"):  f"Monitor {country_iso} — tension trajectory unclear.",
        ("safe_haven","LONG"):   "Flight-to-safety demand rises with elevated geopolitical risk.",
        ("safe_haven","REDUCE"): "Low tension reduces gold/safe-haven premium.",
        ("safe_haven","WATCH"):  "Safe-haven as precautionary hedge; watch for escalation.",
        ("sector","LONG"):   f"Supply disruption risk from {news_type} event supports this sector.",
        ("sector","SHORT"):  f"Sanctions / trade restrictions weigh on this sector.",
        ("sector","WATCH"):  f"Sector sensitive to {news_type} developments; wait for confirmation.",
    }
    return templates.get((role, direction), "Monitor for further developments.")


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
        tension_score:    0–1 from the scoring pipeline
        news_type:        classifier output
        regime:           market regime from detector (CALM/RISING/STRESSED/CRISIS)
        model_confidence: calibrated P(vol_up_3d) from LightGBM, optional

    Returns:
        List of signal dicts — at most 3 (local, safe_haven, sector)
    """
    iso   = iso.upper()
    entry = INDEX_MAP.get(iso, _DEFAULT_ENTRY)
    tier  = entry["tier"]

    display_ticker, tradeable_etf = entry["local_index"]
    safe_haven_ticker             = entry["safe_haven"]
    sector_ticker                 = entry["sector_proxy"]

    strength = _compute_signal_strength(tension_score, regime, news_type)

    # If model gave a confidence, blend it in (weighted average)
    if model_confidence is not None:
        strength = round(0.6 * strength + 0.4 * model_confidence, 4)

    signals: list[dict] = []

    # ── 1. Local equity index signal ──────────────────────────
    if tier in (1, 2):
        direction = _direction_for_local(strength, news_type)
        price_data = _fetch_price(tradeable_etf)
        index_ctx  = _fetch_index_context(display_ticker) if tier == 1 else {}
        signals.append({
            "role":           "local_equity",
            "ticker":         tradeable_etf,
            "name":           _ticker_name(tradeable_etf),
            "direction":      direction,
            "signal_strength": strength,
            "rationale":      _rationale("local", direction, strength, news_type, iso),
            **price_data,
            **index_ctx,
        })
    else:
        # Tier 3: note that direct local equity is inaccessible
        signals.append({
            "role":           "local_equity",
            "ticker":         tradeable_etf,
            "name":           _ticker_name(tradeable_etf) + " (EM Proxy)",
            "direction":      _direction_for_local(strength, news_type),
            "signal_strength": strength,
            "rationale":      (
                f"No direct instrument for {iso} equities. "
                f"Using Emerging Market ETF as a regional proxy."
            ),
            **_fetch_price(tradeable_etf),
        })

    # ── 2. Safe-haven signal ──────────────────────────────────
    direction_sh = _direction_for_safe_haven(strength)
    signals.append({
        "role":           "safe_haven",
        "ticker":         safe_haven_ticker,
        "name":           _ticker_name(safe_haven_ticker),
        "direction":      direction_sh,
        "signal_strength": strength,
        "rationale":      _rationale("safe_haven", direction_sh, strength, news_type, iso),
        **_fetch_price(safe_haven_ticker),
    })

    # ── 3. Sector proxy signal ────────────────────────────────
    direction_sec = _direction_for_sector(strength, news_type, sector_ticker)
    signals.append({
        "role":           "sector_proxy",
        "ticker":         sector_ticker,
        "name":           _ticker_name(sector_ticker),
        "direction":      direction_sec,
        "signal_strength": strength,
        "rationale":      _rationale("sector", direction_sec, strength, news_type, iso),
        **_fetch_price(sector_ticker),
    })

    # Sort: LONG/SHORT before WATCH/REDUCE
    order = {"LONG": 0, "SHORT": 1, "REDUCE": 2, "WATCH": 3}
    return sorted(signals, key=lambda s: order.get(s["direction"], 4))


# ── Ticker display names ──────────────────────────────────────

_NAMES: dict[str, str] = {
    "SPY":   "S&P 500 ETF",
    "QQQ":   "Nasdaq 100 ETF",
    "GLD":   "Gold ETF",
    "USO":   "US Oil Fund ETF",
    "WEAT":  "Wheat ETF",
    "SMH":   "Semiconductor ETF",
    "LMT":   "Lockheed Martin (Defence)",
    "EEM":   "iShares Emerging Markets ETF",
    "INDA":  "iShares MSCI India ETF",
    "FXI":   "iShares China Large-Cap ETF",
    "EWT":   "iShares MSCI Taiwan ETF",
    "EWJ":   "iShares MSCI Japan ETF",
    "EWU":   "iShares MSCI UK ETF",
    "EWG":   "iShares MSCI Germany ETF",
    "EWQ":   "iShares MSCI France ETF",
    "EWY":   "iShares MSCI South Korea ETF",
    "EWZ":   "iShares MSCI Brazil ETF",
    "EWW":   "iShares MSCI Mexico ETF",
    "EWD":   "iShares MSCI Sweden ETF",
    "EIS":   "iShares MSCI Israel ETF",
    "KSA":   "iShares MSCI Saudi Arabia ETF",
    "TUR":   "iShares MSCI Turkey ETF",
    "EPOL":  "iShares MSCI Poland ETF",
    "GREK":  "Global X MSCI Greece ETF",
    "EGPT":  "VanEck Egypt ETF",
    "EZA":   "iShares MSCI South Africa ETF",
    "ARGT":  "Global X MSCI Argentina ETF",
    "GXG":   "Global X MSCI Colombia ETF",
    "EIDO":  "iShares MSCI Indonesia ETF",
    "EPHE":  "iShares MSCI Philippines ETF",
    "ERUS":  "iShares MSCI Russia ETF (halted)",
}


def _ticker_name(ticker: str) -> str:
    return _NAMES.get(ticker, ticker)
