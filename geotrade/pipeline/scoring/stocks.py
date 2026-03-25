"""
pipeline/scoring/stocks.py
───────────────────────────
Maps country ISO → relevant tickers and returns trade signals.

Logic:
 - High tension (>0.7)  → defence/gold UP, local ETF DOWN → SHORT local, LONG safe-havens
 - Medium tension (0.4–0.7) → WATCH list with elevated caution
 - Low tension (<0.4)  → LONG local ETF, SHORT safe-havens

Modifiers:
 - news_type == "sanctions"  → add FX/currency ETF SHORT
 - news_type == "military"   → add defence stocks LONG
 - news_type == "economic"   → add commodity/energy tickers

Uses yfinance for live price + 5-day return.
"""

from __future__ import annotations

import yfinance as yf
from datetime import datetime, timedelta, timezone

# ── Country ISO → relevant tickers ───────────────────────────
COUNTRY_STOCK_MAP: dict[str, list[dict]] = {
    "US": [
        {"ticker": "SPY",  "name": "S&P 500 ETF",         "type": "equity_index"},
        {"ticker": "QQQ",  "name": "Nasdaq 100 ETF",       "type": "equity_index"},
        {"ticker": "LMT",  "name": "Lockheed Martin",      "type": "defence"},
        {"ticker": "RTX",  "name": "Raytheon Technologies", "type": "defence"},
        {"ticker": "GLD",  "name": "Gold ETF",             "type": "safe_haven"},
    ],
    "RU": [
        {"ticker": "ERUS", "name": "iShares MSCI Russia",  "type": "country_etf"},
        {"ticker": "GLD",  "name": "Gold ETF",             "type": "safe_haven"},
        {"ticker": "XOM",  "name": "ExxonMobil (oil)",     "type": "energy"},
        {"ticker": "USO",  "name": "US Oil Fund",          "type": "energy"},
        {"ticker": "LMT",  "name": "Lockheed Martin",      "type": "defence"},
    ],
    "CN": [
        {"ticker": "FXI",  "name": "iShares China Large-Cap", "type": "country_etf"},
        {"ticker": "MCHI", "name": "MSCI China ETF",          "type": "country_etf"},
        {"ticker": "SMH",  "name": "Semiconductor ETF",       "type": "sector"},
        {"ticker": "GLD",  "name": "Gold ETF",               "type": "safe_haven"},
        {"ticker": "LMT",  "name": "Lockheed Martin",        "type": "defence"},
    ],
    "UA": [
        {"ticker": "GLD",  "name": "Gold ETF",             "type": "safe_haven"},
        {"ticker": "USO",  "name": "US Oil Fund",          "type": "energy"},
        {"ticker": "LMT",  "name": "Lockheed Martin",      "type": "defence"},
        {"ticker": "NOC",  "name": "Northrop Grumman",     "type": "defence"},
        {"ticker": "WEAT", "name": "Wheat ETF",            "type": "commodity"},
    ],
    "IR": [
        {"ticker": "USO",  "name": "US Oil Fund",          "type": "energy"},
        {"ticker": "GLD",  "name": "Gold ETF",             "type": "safe_haven"},
        {"ticker": "LMT",  "name": "Lockheed Martin",      "type": "defence"},
        {"ticker": "VDE",  "name": "Vanguard Energy ETF",  "type": "energy"},
    ],
    "IL": [
        {"ticker": "EIS",  "name": "iShares MSCI Israel",  "type": "country_etf"},
        {"ticker": "GLD",  "name": "Gold ETF",             "type": "safe_haven"},
        {"ticker": "LMT",  "name": "Lockheed Martin",      "type": "defence"},
        {"ticker": "USO",  "name": "US Oil Fund",          "type": "energy"},
    ],
    "KP": [
        {"ticker": "GLD",  "name": "Gold ETF",             "type": "safe_haven"},
        {"ticker": "EWJ",  "name": "iShares MSCI Japan",   "type": "country_etf"},
        {"ticker": "EWY",  "name": "iShares MSCI S. Korea","type": "country_etf"},
        {"ticker": "LMT",  "name": "Lockheed Martin",      "type": "defence"},
    ],
    "TW": [
        {"ticker": "EWT",  "name": "iShares MSCI Taiwan",  "type": "country_etf"},
        {"ticker": "SMH",  "name": "Semiconductor ETF",    "type": "sector"},
        {"ticker": "GLD",  "name": "Gold ETF",             "type": "safe_haven"},
        {"ticker": "LMT",  "name": "Lockheed Martin",      "type": "defence"},
    ],
    "IN": [
        {"ticker": "INDA", "name": "iShares MSCI India",   "type": "country_etf"},
        {"ticker": "GLD",  "name": "Gold ETF",             "type": "safe_haven"},
        {"ticker": "USO",  "name": "US Oil Fund",          "type": "energy"},
    ],
    "PK": [
        {"ticker": "GLD",  "name": "Gold ETF",             "type": "safe_haven"},
        {"ticker": "INDA", "name": "iShares MSCI India",   "type": "country_etf"},
        {"ticker": "USO",  "name": "US Oil Fund",          "type": "energy"},
    ],
    "SA": [
        {"ticker": "KSA",  "name": "iShares MSCI Saudi Arabia", "type": "country_etf"},
        {"ticker": "USO",  "name": "US Oil Fund",               "type": "energy"},
        {"ticker": "GLD",  "name": "Gold ETF",                  "type": "safe_haven"},
    ],
    "TR": [
        {"ticker": "TUR",  "name": "iShares MSCI Turkey",  "type": "country_etf"},
        {"ticker": "GLD",  "name": "Gold ETF",             "type": "safe_haven"},
        {"ticker": "USO",  "name": "US Oil Fund",          "type": "energy"},
    ],
    "VE": [
        {"ticker": "GLD",  "name": "Gold ETF",             "type": "safe_haven"},
        {"ticker": "USO",  "name": "US Oil Fund",          "type": "energy"},
        {"ticker": "EEM",  "name": "iShares Emerging Mkts","type": "country_etf"},
    ],
    "MM": [
        {"ticker": "EEM",  "name": "iShares Emerging Mkts","type": "country_etf"},
        {"ticker": "GLD",  "name": "Gold ETF",             "type": "safe_haven"},
    ],
}

# Fallback tickers for unlisted countries
_DEFAULT_TICKERS: list[dict] = [
    {"ticker": "GLD",  "name": "Gold ETF",              "type": "safe_haven"},
    {"ticker": "EEM",  "name": "iShares Emerging Mkts", "type": "country_etf"},
    {"ticker": "LMT",  "name": "Lockheed Martin",       "type": "defence"},
    {"ticker": "USO",  "name": "US Oil Fund",           "type": "energy"},
]

# ── Signal logic per type ─────────────────────────────────────
def _direction(ticker_type: str, tension: float, news_type: str) -> str:
    """Determine LONG / SHORT / WATCH based on context."""
    is_high    = tension >= 0.65
    is_medium  = 0.35 <= tension < 0.65

    safe_havens = {"safe_haven"}
    defence     = {"defence"}
    local_etf   = {"country_etf", "equity_index"}
    energy      = {"energy"}
    commodity   = {"commodity"}

    if ticker_type in safe_havens:
        return "LONG" if is_high else ("WATCH" if is_medium else "SHORT")
    if ticker_type in defence:
        return "LONG" if is_high else "WATCH"
    if ticker_type in local_etf:
        if news_type in ("sanctions", "conflict", "military"):
            return "SHORT" if is_high else "WATCH"
        return "WATCH" if is_high else "LONG"
    if ticker_type in energy:
        if news_type in ("conflict", "military"):
            return "LONG" if is_high else "WATCH"
        return "WATCH"
    if ticker_type in commodity:
        return "LONG" if is_high else "WATCH"
    return "WATCH"


def _rationale(ticker_type: str, direction: str, tension: float, news_type: str) -> str:
    templates = {
        ("safe_haven", "LONG"):    "Flight-to-safety demand rises with high tension",
        ("safe_haven", "SHORT"):   "Low tension reduces safe-haven premium",
        ("safe_haven", "WATCH"):   "Monitor as volatility may spike",
        ("defence",    "LONG"):    "Defence spending rises during military/conflict events",
        ("defence",    "WATCH"):   "Watch for escalation signals before entry",
        ("country_etf","SHORT"):   f"{'Sanctions' if news_type=='sanctions' else 'Conflict'} pressure weighs on domestic equities",
        ("country_etf","LONG"):    "Tension easing supports local market recovery",
        ("country_etf","WATCH"):   "Monitor tension trajectory before committing",
        ("energy",     "LONG"):    "Supply disruption risk supports oil/energy prices",
        ("energy",     "WATCH"):   "Energy markets sensitive to geopolitical developments",
        ("commodity",  "LONG"):    "Conflict disrupts agricultural supply chains",
        ("commodity",  "WATCH"):   "Monitor for supply-side disruptions",
    }
    return templates.get((ticker_type, direction), "Monitor for developments")


def _fetch_price_data(ticker: str) -> dict:
    """Fetch current price and 5-day change from yfinance."""
    try:
        end   = datetime.now(timezone.utc)
        start = end - timedelta(days=10)
        df = yf.download(
            ticker,
            start=start.strftime("%Y-%m-%d"),
            end=end.strftime("%Y-%m-%d"),
            progress=False,
            auto_adjust=True,
        )
        if df.empty:
            return {"price": None, "change_5d": None, "error": "no data"}
        # Flatten multi-level columns if present
        if hasattr(df.columns, "get_level_values"):
            df.columns = df.columns.get_level_values(0)
        close = df["Close"].dropna()
        if len(close) < 2:
            return {"price": round(float(close.iloc[-1]), 2), "change_5d": None}
        latest   = float(close.iloc[-1])
        prev_5d  = float(close.iloc[max(0, len(close) - 6)])
        change   = round((latest - prev_5d) / prev_5d * 100, 2)
        return {"price": round(latest, 2), "change_5d": change}
    except Exception as e:
        return {"price": None, "change_5d": None, "error": str(e)}


def get_stock_signals(
    iso: str,
    tension_score: float,
    news_type: str = "other",
    max_tickers: int = 5,
) -> list[dict]:
    """
    Return ranked list of stock signals for a country ISO code.

    Args:
        iso:           Country ISO-2 code (e.g. 'RU', 'CN')
        tension_score: 0–1 float from the scoring pipeline
        news_type:     classifier output (conflict/sanctions/military/etc.)
        max_tickers:   how many tickers to return

    Returns:
        List of dicts with ticker, name, price, change_5d, direction, rationale
    """
    candidates = COUNTRY_STOCK_MAP.get(iso.upper(), _DEFAULT_TICKERS)[:max_tickers]

    signals = []
    for item in candidates:
        ticker = item["ticker"]
        t_type = item["type"]
        direction = _direction(t_type, tension_score, news_type)
        rationale = _rationale(t_type, direction, tension_score, news_type)
        price_data = _fetch_price_data(ticker)

        signals.append({
            "ticker":    ticker,
            "name":      item["name"],
            "type":      t_type,
            "direction": direction,
            "rationale": rationale,
            **price_data,
        })

    # Sort: LONG/SHORT before WATCH, then by absolute 5d change
    def sort_key(s):
        order = {"LONG": 0, "SHORT": 1, "WATCH": 2}
        chg   = abs(s.get("change_5d") or 0)
        return (order.get(s["direction"], 3), -chg)

    return sorted(signals, key=sort_key)
