"""
pipeline/modeling/features.py
───────────────────────────────
Loads tension signals + market data and builds the feature matrix.

News-type features added (2026-03):
  news_type_conflict, news_type_sanctions, news_type_economic,
  news_type_military — binary flags aggregated per day.
"""

import numpy as np
import pandas as pd
import yfinance as yf

from config.settings import settings
from pipeline.utils.db import get_db
from pipeline.nlp.classifier import classify_news_type


# ── Feature column names ─────────────────────────────────────
FEATURE_COLS = [
    "global_tension",
    "max_tension",
    "avg_neg_sentiment",
    "conflict_count",
    "n_countries",
    "total_events",
    "tension_lag_1d",
    "tension_lag_2d",
    "tension_lag_3d",
    "vix_pct_change",
    "sp500_volatility_5d",
    # News-type binary features
    "news_type_conflict",
    "news_type_sanctions",
    "news_type_economic",
    "news_type_military",
]
TARGET_COL = "volatility_increase"


def _add_news_type_features(tension_df: pd.DataFrame) -> pd.DataFrame:
    """
    Enrich tension_df with news-type binary columns by joining against
    the processed_events collection and counting event types per day.
    Falls back to zeros if collection is empty.
    """
    try:
        db   = get_db()
        docs = list(db[settings.COL_PROCESSED_EVENTS].find({}, {"_id": 0, "date": 1, "title": 1}))
        if not docs:
            raise ValueError("empty")
        art_df = pd.DataFrame(docs)
        art_df["date"] = pd.to_datetime(art_df["date"].str[:10], errors="coerce")
        art_df["news_type"] = art_df["title"].fillna("").apply(classify_news_type)

        type_dummies  = pd.get_dummies(art_df["news_type"], prefix="news_type")
        art_df        = pd.concat([art_df[["date"]], type_dummies], axis=1)
        type_per_day  = art_df.groupby("date").sum().reset_index()

        # Ensure all expected columns exist
        for col in ["news_type_conflict", "news_type_sanctions",
                    "news_type_economic",  "news_type_military"]:
            if col not in type_per_day.columns:
                type_per_day[col] = 0

        tension_df = tension_df.merge(type_per_day, on="date", how="left")
    except Exception:
        for col in ["news_type_conflict", "news_type_sanctions",
                    "news_type_economic",  "news_type_military"]:
            tension_df[col] = 0

    fill_cols = ["news_type_conflict", "news_type_sanctions",
                 "news_type_economic",  "news_type_military"]
    tension_df[fill_cols] = tension_df[fill_cols].fillna(0).astype(int)
    return tension_df


def load_tension_df() -> pd.DataFrame:
    """
    Load daily_signals from MongoDB and aggregate globally per date.
    Falls back to CSV if MongoDB is empty.
    Adds news-type binary features for improved model accuracy.
    """
    db = get_db()
    docs = list(db[settings.COL_DAILY_SIGNALS].find({}, {"_id": 0}))

    if not docs:
        csv_path = settings.DATA_PROCESSED / "daily_signals.csv"
        if csv_path.exists():
            return pd.read_csv(csv_path, parse_dates=["date"])
        raise RuntimeError("No daily_signals found. Run step 3 first.")

    df = pd.DataFrame(docs)
    df["date"] = pd.to_datetime(df["date"])

    agg = (
        df.groupby("date")
        .agg(
            global_tension    = ("tension_score",    "mean"),
            max_tension       = ("tension_score",    "max"),
            total_events      = ("event_count",      "sum"),
            conflict_count    = ("conflict_count",   "sum"),
            avg_neg_sentiment = ("avg_neg_sentiment","mean"),
            n_countries       = ("iso",              "nunique"),
        )
        .reset_index()
    )

    return _add_news_type_features(agg)


def download_market_df(start: str, end: str) -> pd.DataFrame:
    """Download VIX + S&P500 via yfinance and compute derived features."""
    def _get_close(ticker: str) -> pd.Series:
        raw = yf.download(ticker, start=start, end=end, progress=False, auto_adjust=True)
        # yfinance v1.x returns multi-level columns: (Price, Ticker)
        if isinstance(raw.columns, pd.MultiIndex):
            raw.columns = raw.columns.get_level_values(0)
        return raw["Close"]

    vix_close   = _get_close("^VIX").rename("vix_close")
    sp500_close = _get_close("^GSPC").rename("sp500_close")

    mkt = pd.concat([vix_close, sp500_close], axis=1).ffill().dropna().reset_index()
    mkt.rename(columns={"Date": "date", "index": "date", "Datetime": "date"}, inplace=True)
    # Handle any remaining multi-level index column
    if "date" not in mkt.columns:
        mkt = mkt.rename(columns={mkt.columns[0]: "date"})
    mkt["date"] = pd.to_datetime(mkt["date"])

    mkt["vix_pct_change"]      = mkt["vix_close"].pct_change()
    mkt["sp500_returns"]       = mkt["sp500_close"].pct_change()
    mkt["sp500_volatility_5d"] = mkt["sp500_returns"].rolling(5).std()
    mkt["next_day_vix"]        = mkt["vix_close"].shift(-1)
    mkt[TARGET_COL]            = (mkt["next_day_vix"] > mkt["vix_close"]).astype(int)

    return mkt.dropna()


def synthetic_market_df(tension_df: pd.DataFrame) -> pd.DataFrame:
    """Synthetic market data for offline development / testing."""
    dates = pd.bdate_range(tension_df["date"].min(), tension_df["date"].max())
    rng   = np.random.RandomState(42)
    vix   = np.clip(20 + np.cumsum(rng.randn(len(dates)) * 0.5), 10, 80)
    sp500 = 4000 + np.cumsum(rng.randn(len(dates)) * 15)

    df = pd.DataFrame({"date": dates, "vix_close": vix, "sp500_close": sp500})
    df["vix_pct_change"]      = df["vix_close"].pct_change()
    df["sp500_returns"]       = df["sp500_close"].pct_change()
    df["sp500_volatility_5d"] = df["sp500_returns"].rolling(5).std()
    df["next_day_vix"]        = df["vix_close"].shift(-1)
    df[TARGET_COL]            = (df["next_day_vix"] > df["vix_close"]).astype(int)
    return df.dropna()


def build_merged(tension_df: pd.DataFrame, market_df: pd.DataFrame) -> pd.DataFrame:
    """Merge and add lagged tension features."""
    merged = market_df.merge(tension_df, on="date", how="left").ffill()
    for lag in [1, 2, 3]:
        merged[f"tension_lag_{lag}d"] = merged["global_tension"].shift(lag)
    return merged.dropna()


def split_features(merged: pd.DataFrame):
    """Return X_train, X_test, y_train, y_test (chronological split 80/20)."""
    cols = [c for c in FEATURE_COLS if c in merged.columns]
    X = merged[cols].values
    y = merged[TARGET_COL].values
    split = int(len(X) * 0.8)
    return X[:split], X[split:], y[:split], y[split:], cols
