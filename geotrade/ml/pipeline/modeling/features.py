"""
pipeline/modeling/features.py
───────────────────────────────
Loads tension signals + market data and builds the 25-feature matrix.

Feature groups:
  [5]  Tension level    — global_tension, max_tension, weighted_tension,
                          n_high_tension_countries, tension_concentration
  [4]  Tension velocity — velocity_7d, velocity_3d, lag_1d, lag_7d
  [5]  News composition — conflict/military/sanctions/economic flags + intensity
  [6]  Market condition — vix_level, vix_pct_change, vix_7d_ma,
                          vix_above_20, vix_above_30, sp500_volatility_5d
  [3]  Regime           — market_regime, tension_regime, days_in_regime
  [2]  Interaction      — tension_x_vix, high_tension_stressed_mkt

Target: vol_up_3d — 1 if VIX is higher 3 days from now, else 0
  (3-day window reduces noise vs 1-day; captures delayed geopolitical transmission)
"""

import numpy as np
import pandas as pd
import yfinance as yf

from config.settings import settings
from pipeline.utils.db import get_db
from pipeline.nlp.classifier import classify_news_type


# ── Feature columns (order matters — used by train.py) ───────
FEATURE_COLS = [
    # Tension level (5)
    "global_tension",
    "max_tension",
    "weighted_tension",
    "n_high_tension_countries",
    "tension_concentration",
    # Tension velocity / momentum (4)
    "tension_velocity_7d",
    "tension_velocity_3d",
    "tension_lag_1d",
    "tension_lag_7d",
    # News composition (5)
    "news_type_conflict",
    "news_type_military",
    "news_type_sanctions",
    "news_type_economic",
    "conflict_intensity",
    # Market condition (6)
    "vix_level",
    "vix_pct_change",
    "vix_7d_ma",
    "vix_above_20",
    "vix_above_30",
    "sp500_volatility_5d",
    # Regime (3)
    "market_regime",
    "tension_regime_num",
    "days_in_current_regime",
    # Interaction (2)
    "tension_x_vix",
    "high_tension_stressed_mkt",
]

TARGET_COL = "vol_up_3d"   # 3-day forward VIX direction (less noisy than 1-day)


# ── Tension regime encoder ────────────────────────────────────

def _encode_tension_regime(score: float, velocity: float) -> int:
    """
    CALM=0, RISING=1, PEAK=2, COOLING=3
    Based on tension level + velocity direction.
    """
    if score >= 0.65:
        return 2  # PEAK
    if score < 0.35 and abs(velocity) < 0.02:
        return 0  # CALM
    if velocity > 0.02:
        return 1  # RISING
    if velocity < -0.02:
        return 3  # COOLING
    return 1  # default to RISING for middle ground


def _market_regime(vix: float) -> int:
    """0=CALM, 1=RISING, 2=STRESSED, 3=CRISIS"""
    if vix < 18:
        return 0
    if vix < 25:
        return 1
    if vix < 35:
        return 2
    return 3


def _days_in_regime(regime_series: pd.Series) -> pd.Series:
    """Count how many consecutive days we've been in the current regime."""
    result = []
    count = 1
    for i, val in enumerate(regime_series):
        if i == 0:
            result.append(1)
            continue
        if val == regime_series.iloc[i - 1]:
            count += 1
        else:
            count = 1
        result.append(count)
    return pd.Series(result, index=regime_series.index)


# ── News type features ────────────────────────────────────────

def _add_news_type_features(tension_df: pd.DataFrame) -> pd.DataFrame:
    """
    Enrich tension_df with news-type binary columns + conflict_intensity.
    Falls back to zeros if collection is empty.
    """
    try:
        db   = get_db()
        docs = list(db[settings.COL_PROCESSED_EVENTS].find(
            {}, {"_id": 0, "date": 1, "published_at": 1, "title": 1, "event_count": 1}
        ))
        if not docs:
            raise ValueError("empty")
        art_df = pd.DataFrame(docs)
        # Use published_at if date is missing
        if "date" not in art_df.columns:
            art_df["date"] = art_df.get("published_at", pd.Series(dtype="object"))
        art_df["date"] = pd.to_datetime(art_df["date"].str[:10], errors="coerce")
        art_df.dropna(subset=["date"], inplace=True)
        art_df["news_type"] = art_df["title"].fillna("").apply(classify_news_type)

        type_dummies = pd.get_dummies(art_df["news_type"], prefix="news_type")
        art_df       = pd.concat([art_df[["date"]], type_dummies], axis=1)
        type_per_day = art_df.groupby("date").sum().reset_index()

        for col in ["news_type_conflict", "news_type_sanctions",
                    "news_type_economic", "news_type_military"]:
            if col not in type_per_day.columns:
                type_per_day[col] = 0

        tension_df = tension_df.merge(type_per_day, on="date", how="left")
    except Exception:
        for col in ["news_type_conflict", "news_type_sanctions",
                    "news_type_economic", "news_type_military"]:
            tension_df[col] = 0

    fill_cols = ["news_type_conflict", "news_type_sanctions",
                 "news_type_economic", "news_type_military"]
    tension_df[fill_cols] = tension_df[fill_cols].fillna(0).astype(int)

    # conflict_intensity = conflict events / total events (ratio, not raw count)
    tension_df["conflict_intensity"] = (
        tension_df["conflict_count"] / tension_df["total_events"].clip(lower=1)
    ).fillna(0).round(4)

    return tension_df


# ── Tension loader ────────────────────────────────────────────

def load_tension_df() -> pd.DataFrame:
    """
    Load daily_signals from MongoDB and aggregate globally per date.
    Adds velocity, regime, and news-type features.
    Falls back to CSV if MongoDB is empty.
    """
    db   = get_db()
    docs = list(db[settings.COL_DAILY_SIGNALS].find({}, {"_id": 0}))

    if not docs:
        csv_path = settings.DATA_PROCESSED / "daily_signals.csv"
        if csv_path.exists():
            return pd.read_csv(csv_path, parse_dates=["date"])
        raise RuntimeError("No daily_signals found. Run step 3 first.")

    df = pd.DataFrame(docs)
    df["date"] = pd.to_datetime(df["date"])

    # Country-importance weighting: give more weight to countries with
    # higher event counts (proxy for geopolitical salience)
    df["weight"] = df["event_count"].clip(lower=1)
    df["weighted_score"] = df["tension_score"] * df["weight"]

    agg = (
        df.groupby("date")
        .agg(
            global_tension           = ("tension_score",     "mean"),
            max_tension              = ("tension_score",     "max"),
            weighted_sum             = ("weighted_score",    "sum"),
            weight_total             = ("weight",            "sum"),
            total_events             = ("event_count",       "sum"),
            conflict_count           = ("conflict_count",    "sum"),
            avg_neg_sentiment        = ("avg_neg_sentiment", "mean"),
            n_countries              = ("iso",               "nunique"),
            n_high_tension_countries = ("tension_score",     lambda x: (x >= 0.65).sum()),
            tension_concentration    = ("tension_score",     "std"),   # std across countries
        )
        .reset_index()
    )

    # weighted_tension = importance-weighted average
    agg["weighted_tension"]    = (agg["weighted_sum"] / agg["weight_total"].clip(lower=1)).round(4)
    agg["tension_concentration"] = agg["tension_concentration"].fillna(0).round(4)

    # ── Velocity features ─────────────────────────────────────
    agg.sort_values("date", inplace=True)
    agg.reset_index(drop=True, inplace=True)
    agg["tension_lag_1d"]       = agg["global_tension"].shift(1)
    agg["tension_lag_7d"]       = agg["global_tension"].shift(7)
    agg["tension_velocity_7d"]  = (agg["global_tension"] - agg["tension_lag_7d"]).round(4)
    agg["tension_velocity_3d"]  = (agg["global_tension"] - agg["global_tension"].shift(3)).round(4)

    # ── Tension regime (per global aggregate) ─────────────────
    agg["tension_regime_num"] = [
        _encode_tension_regime(row["global_tension"], row["tension_velocity_7d"] or 0)
        for _, row in agg.iterrows()
    ]

    # ── News-type features ────────────────────────────────────
    agg = _add_news_type_features(agg)

    return agg


# ── Market data downloader ────────────────────────────────────

def download_market_df(start: str, end: str) -> pd.DataFrame:
    """Download VIX + S&P500 via yfinance and compute all derived market features."""
    def _get_close(ticker: str) -> pd.Series:
        raw = yf.download(ticker, start=start, end=end, progress=False, auto_adjust=True)
        if isinstance(raw.columns, pd.MultiIndex):
            raw.columns = raw.columns.get_level_values(0)
        return raw["Close"]

    vix_close   = _get_close("^VIX").rename("vix_close")
    sp500_close = _get_close("^GSPC").rename("sp500_close")

    mkt = pd.concat([vix_close, sp500_close], axis=1).ffill().dropna().reset_index()
    mkt.rename(columns={"Date": "date", "index": "date", "Datetime": "date"}, inplace=True)
    if "date" not in mkt.columns:
        mkt = mkt.rename(columns={mkt.columns[0]: "date"})
    mkt["date"] = pd.to_datetime(mkt["date"])

    # Core return / volatility
    mkt["vix_pct_change"]      = mkt["vix_close"].pct_change()
    mkt["sp500_returns"]       = mkt["sp500_close"].pct_change()
    mkt["sp500_volatility_5d"] = mkt["sp500_returns"].rolling(5).std()

    # NEW: VIX level features
    mkt["vix_level"]           = mkt["vix_close"]
    mkt["vix_7d_ma"]           = mkt["vix_close"].rolling(7).mean()
    mkt["vix_above_20"]        = (mkt["vix_close"] > 20).astype(int)
    mkt["vix_above_30"]        = (mkt["vix_close"] > 30).astype(int)

    # NEW: Market regime (numeric)
    mkt["market_regime"]       = mkt["vix_close"].apply(_market_regime)

    # NEW: Days in current market regime
    mkt["days_in_current_regime"] = _days_in_regime(mkt["market_regime"])

    # NEW: Target — 3-day forward VIX (less noise than 1-day)
    mkt["vix_3d_forward"]      = mkt["vix_close"].shift(-3)
    mkt[TARGET_COL]            = (mkt["vix_3d_forward"] > mkt["vix_close"]).astype(int)

    return mkt.dropna()


def synthetic_market_df(tension_df: pd.DataFrame) -> pd.DataFrame:
    """Synthetic market data for offline development / testing."""
    dates = pd.bdate_range(tension_df["date"].min(), tension_df["date"].max())
    rng   = np.random.RandomState(42)

    vix   = np.clip(20 + np.cumsum(rng.randn(len(dates)) * 0.5), 10, 80)
    sp500 = 4000 + np.cumsum(rng.randn(len(dates)) * 15)

    df = pd.DataFrame({"date": dates, "vix_close": vix, "sp500_close": sp500})
    df["vix_pct_change"]         = df["vix_close"].pct_change()
    df["sp500_returns"]          = df["sp500_close"].pct_change()
    df["sp500_volatility_5d"]    = df["sp500_returns"].rolling(5).std()
    df["vix_level"]              = df["vix_close"]
    df["vix_7d_ma"]              = df["vix_close"].rolling(7).mean()
    df["vix_above_20"]           = (df["vix_close"] > 20).astype(int)
    df["vix_above_30"]           = (df["vix_close"] > 30).astype(int)
    df["market_regime"]          = df["vix_close"].apply(_market_regime)
    df["days_in_current_regime"] = _days_in_regime(df["market_regime"])
    df["vix_3d_forward"]         = df["vix_close"].shift(-3)
    df[TARGET_COL]               = (df["vix_3d_forward"] > df["vix_close"]).astype(int)
    return df.dropna()


# ── Merge + interaction terms ─────────────────────────────────

def build_merged(tension_df: pd.DataFrame, market_df: pd.DataFrame) -> pd.DataFrame:
    """Merge tension + market data; add interaction features."""
    merged = market_df.merge(tension_df, on="date", how="left").ffill()

    # Fill any tension columns that didn't join (early dates)
    for col in ["global_tension", "max_tension", "weighted_tension"]:
        if col in merged.columns:
            merged[col] = merged[col].fillna(0)

    # ── Interaction features ──────────────────────────────────
    merged["tension_x_vix"] = (
        merged["global_tension"] * merged["vix_level"]
    ).round(4)
    merged["high_tension_stressed_mkt"] = (
        ((merged["global_tension"] >= 0.65) & (merged["vix_close"] >= 25)).astype(int)
    )

    # Fill remaining NaNs in velocity / lag columns
    vel_cols = ["tension_velocity_7d", "tension_velocity_3d", "tension_lag_1d", "tension_lag_7d"]
    merged[vel_cols] = merged[vel_cols].fillna(0)

    # tension_regime_num may not exist if tension_df was loaded from CSV
    if "tension_regime_num" not in merged.columns:
        merged["tension_regime_num"] = merged.get("global_tension", pd.Series(0)).apply(
            lambda t: _encode_tension_regime(t, 0)
        )

    return merged.dropna(subset=[TARGET_COL])


# ── Train/test split ──────────────────────────────────────────

def split_features(merged: pd.DataFrame):
    """
    Return X, y arrays using available FEATURE_COLS.
    Preserves chronological order — do NOT shuffle.
    TimeSeriesSplit CV should be applied in train.py.
    """
    cols = [c for c in FEATURE_COLS if c in merged.columns]
    X    = merged[cols].values
    y    = merged[TARGET_COL].values
    # 80/20 chronological split (inner CV handled by TimeSeriesSplit in train.py)
    split = int(len(X) * 0.8)
    return X[:split], X[split:], y[:split], y[split:], cols
