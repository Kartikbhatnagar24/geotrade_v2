#!/usr/bin/env python3
"""
Run the full prediction pipeline end-to-end:
  1. Download fresh GDELT data (last N days)
  2. Build rolling features
  3. Download latest market prices + VIX
  4. Build breadth features
  5. Engineer derived features (same logic as training, no labels needed)
  6. Take the latest row per country
  7. Run through the trained ensemble
  8. Store predictions in MongoDB

Run from the geotrade root:
    python ml/scripts/models/run_predict.py
"""

from __future__ import annotations

import argparse
import bisect
import csv
import datetime as dt
import json
import math
import subprocess
import sys
from collections import defaultdict, deque
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from pymongo import MongoClient, UpdateOne

# ── Paths ─────────────────────────────────────────────────────────────────────
ROOT        = Path(__file__).parents[3]
ML_DATA     = ROOT / "ml" / "data"
PROCESSED   = ML_DATA / "processed"
WORKING     = ML_DATA / "working"
MARKET_RAW  = ML_DATA / "market" / "raw"
MODEL_DIR   = ML_DATA / "models"
CONFIG_DIR  = ROOT / "config"
MAPPING_CSV = CONFIG_DIR / "country_asset_mapping.csv"

GDELT_DAILY_CSV   = PROCESSED / "gdelt_predict_daily.csv"
ROLLING_CSV       = PROCESSED / "gdelt_predict_rolling.csv"
BREADTH_CSV       = WORKING   / "gdelt_predict_breadth.csv"
INFERENCE_CSV     = WORKING   / "gdelt_inference_latest.csv"

SCRIPTS = ROOT / "ml" / "scripts"

ALL_LABEL_COLUMNS  = ["label_up_3d", "label_vol_high_5d", "label_has_market_data"]
META_COLUMNS       = ["date", "country_code", "asset_symbol"] + ALL_LABEL_COLUMNS
CATEGORICAL_COLUMNS = ["country_code", "asset_symbol"]

# ── Thesis feature set (Section 4.3, f1–f30) — mirrors build_training_dataset.py
THESIS_BASE_FEATURES: set[str] = {
    # Tension-Level (f1–f5)
    "avg_tone_mean_mean_14d", "tone_range_14d",
    "breadth_high_news_frac", "breadth_countries_active", "breadth_neg_tone_frac",
    # Velocity/Momentum (f6–f9)
    "avg_tone_mean_3d_minus_14d", "document_count_3d_vs_14d",
    "theme_mentions_3d_vs_14d", "cameo_event_mentions_3d_vs_14d",
    # News Composition (f10–f14)
    "document_count_sum_14d", "cameo_event_mentions_sum_14d",
    "theme_density_14d", "news_intensity_14d", "cameo_event_mentions_vs_14d",
    # Market Condition (f15–f20)
    "vix_close", "vix_change_1d",
    "market_volatility_5d", "market_momentum_5d",
    "market_prev_return_1d", "market_prev_return_3d",
    # Regime / Interaction (f21–f25)
    "document_count_vs_14d", "source_diversity_ratio",
    "person_diversity_ratio", "tone_range", "person_mentions_3d_vs_14d",
}

# NLP tension features (f26–f30) + helper flag
TENSION_COLS: list[str] = [
    "tension_score",       # f26
    "smoothed_score",      # f27
    "avg_neg_sentiment",   # f28
    "conflict_gravity",    # f29
    "nlp_event_count",     # f30
    "has_tension_data",    # helper: 1 = real BART output, 0 = default
]
TENSION_DEFAULTS: dict = {
    "tension_score":     0.5,
    "smoothed_score":    0.5,
    "avg_neg_sentiment": 0.0,
    "conflict_gravity":  0.0,
    "nlp_event_count":   0,
    "has_tension_data":  0,
}

_META_COLS: set[str] = {
    "date", "country_code", "asset_symbol",
    "label_up_3d", "label_vol_high_5d", "label_has_market_data",
}
_ALL_ALLOWED: set[str] = _META_COLS | THESIS_BASE_FEATURES | set(TENSION_COLS)


# ── Step helpers ───────────────────────────────────────────────────────────────

def run(script: Path, *args: str) -> None:
    cmd = [sys.executable, str(script), *args]
    print(f"\n[run] {' '.join(cmd)}")
    result = subprocess.run(cmd, cwd=str(ROOT))
    if result.returncode != 0:
        raise RuntimeError(f"Script failed: {script.name}")


def load_mapping() -> dict[str, dict]:
    mapping = {}
    with MAPPING_CSV.open("r", encoding="utf-8", newline="") as f:
        for row in csv.DictReader(f):
            if row.get("enabled", "1") == "1":
                mapping[row["gdelt_country_code"]] = row
    return mapping


def load_market_series(path: Path) -> tuple[list[dt.date], list[float]]:
    dates, closes = [], []
    with path.open("r", encoding="utf-8", newline="") as f:
        for row in csv.DictReader(f):
            try:
                dates.append(dt.datetime.strptime(row["Date"], "%Y-%m-%d").date())
                closes.append(float(row["Close"]))
            except (KeyError, ValueError):
                continue
    return dates, closes


# ── Tension signal loader (NLP pipeline → MongoDB daily_signals + processed_events) ──

def load_tension_signals(db) -> dict[str, dict]:
    """
    Fetch the most recent 5 NLP tension features (f26–f30) per country from
    daily_signals. Returns {iso2_upper: {tension feature dict}}.
    Matches build_training_dataset.py exactly — only thesis NLP columns.
    """
    signal_pipeline = [
        {"$sort": {"date": -1}},
        {"$group": {
            "_id":               "$iso",
            "tension_score":     {"$first": "$tension_score"},
            "smoothed_score":    {"$first": "$smoothed_score"},
            "avg_neg_sentiment": {"$first": "$avg_neg_sentiment"},
            "conflict_gravity":  {"$first": "$conflict_gravity"},
            "event_count":       {"$first": "$event_count"},
        }},
    ]
    signal_docs = list(db["daily_signals"].aggregate(signal_pipeline))

    result: dict[str, dict] = {}
    for doc in signal_docs:
        iso = str(doc.get("_id", "")).upper()
        if not iso:
            continue
        result[iso] = {
            "tension_score":     float(doc.get("tension_score",     TENSION_DEFAULTS["tension_score"])),
            "smoothed_score":    float(doc.get("smoothed_score",    TENSION_DEFAULTS["smoothed_score"])),
            "avg_neg_sentiment": float(doc.get("avg_neg_sentiment", TENSION_DEFAULTS["avg_neg_sentiment"])),
            "conflict_gravity":  float(doc.get("conflict_gravity",  TENSION_DEFAULTS["conflict_gravity"])),
            "nlp_event_count":   int(doc.get("event_count",         TENSION_DEFAULTS["nlp_event_count"])),
            "has_tension_data":  1,
        }

    print(f"[tension] {len(result)} countries with NLP signals from daily_signals")
    return result


# ── Feature engineering (same logic as training scripts, inline) ───────────────

def engineer_row(row: dict) -> dict:
    """Apply the same derived features as engineer_market_features.py."""
    def f(key):
        v = row.get(key, "")
        try: return float(v)
        except: return 0.0

    def ratio(num, den): return num / den if den else 0.0

    doc = f("document_count")
    out = dict(row)

    # Ratios vs 14d
    for raw_key, sum_key, feat in [
        ("document_count",       "document_count_sum_14d",       "document_count_vs_14d"),
        ("theme_mentions",       "theme_mentions_sum_14d",       "theme_mentions_vs_14d"),
        ("person_mentions",      "person_mentions_sum_14d",      "person_mentions_vs_14d"),
        ("organization_mentions","organization_mentions_sum_14d","organization_mentions_vs_14d"),
        ("cameo_event_mentions", "cameo_event_mentions_sum_14d", "cameo_event_mentions_vs_14d"),
    ]:
        out[feat] = ratio(f(raw_key) * 14.0, f(sum_key))

    # Per-doc
    for raw_key, feat in [
        ("theme_mentions",        "theme_mentions_per_doc"),
        ("theme_unique",          "theme_unique_per_doc"),
        ("person_mentions",       "person_mentions_per_doc"),
        ("person_unique",         "person_unique_per_doc"),
        ("organization_mentions", "organization_mentions_per_doc"),
        ("organization_unique",   "organization_unique_per_doc"),
        ("source_mentions",       "source_mentions_per_doc"),
        ("source_unique",         "source_unique_per_doc"),
        ("cameo_event_mentions",  "cameo_event_mentions_per_doc"),
    ]:
        out[feat] = ratio(f(raw_key), doc)

    # 1-day deltas
    for cur, lag, feat in [
        ("document_count",       "document_count_lag1",       "document_count_delta_1d"),
        ("avg_tone_mean",        "avg_tone_mean_lag1",        "avg_tone_mean_delta_1d"),
    ]:
        out[feat] = f(cur) - f(lag)

    # 3d vs 14d trends
    for short, long_, feat in [
        ("document_count_sum_3d",        "document_count_sum_14d",        "document_count_3d_vs_14d"),
        ("theme_mentions_sum_3d",        "theme_mentions_sum_14d",        "theme_mentions_3d_vs_14d"),
        ("person_mentions_sum_3d",       "person_mentions_sum_14d",       "person_mentions_3d_vs_14d"),
        ("organization_mentions_sum_3d", "organization_mentions_sum_14d", "organization_mentions_3d_vs_14d"),
        ("cameo_event_mentions_sum_3d",  "cameo_event_mentions_sum_14d",  "cameo_event_mentions_3d_vs_14d"),
    ]:
        out[feat] = ratio(f(short) * (14.0 / 3.0), f(long_))

    out["avg_tone_mean_3d_minus_14d"] = f("avg_tone_mean_mean_3d") - f("avg_tone_mean_mean_14d")

    out["source_diversity_ratio"]      = ratio(f("source_unique"),       f("source_mentions"))
    out["organization_diversity_ratio"]= ratio(f("organization_unique"), f("organization_mentions"))
    out["person_diversity_ratio"]      = ratio(f("person_unique"),       f("person_mentions"))
    out["theme_density_14d"]           = ratio(f("theme_mentions_sum_14d"),  f("document_count_sum_14d"))
    out["news_intensity_14d"]          = ratio(f("numarts_sum_sum_14d"),     f("document_count_sum_14d"))
    out["tone_range"]                  = f("avg_tone_max") - f("avg_tone_min")
    out["tone_range_14d"]              = f("avg_tone_max_mean_14d") - f("avg_tone_min_mean_14d")

    return out


def add_market_context(row: dict, asset_symbol: str, ref_date: str,
                       market_ctx: dict, vix_data: dict, breadth_data: dict) -> dict:
    """Add market context features — same logic as add_market_context_features.py."""
    out = dict(row)
    for field in ["market_prev_return_1d", "market_prev_return_3d",
                  "market_volatility_5d", "market_momentum_5d",
                  "vix_close", "vix_change_1d",
                  "breadth_high_news_count", "breadth_neg_tone_count",
                  "breadth_high_news_frac", "breadth_neg_tone_frac",
                  "breadth_countries_active"]:
        out[field] = 0.0

    ctx = market_ctx.get((asset_symbol, ref_date))
    if ctx:
        out.update(ctx)

    vix = vix_data.get(ref_date)
    if vix:
        out["vix_close"]     = vix["close"]
        out["vix_change_1d"] = vix["change_1d"]

    gdelt_date = row.get("date", "")
    breadth = breadth_data.get(gdelt_date)
    if breadth:
        out.update(breadth)

    return out


# ── Market context loaders ─────────────────────────────────────────────────────

def build_market_context(market_dir: Path) -> dict:
    context = {}
    for mf in market_dir.glob("*.csv"):
        symbol = mf.stem
        rows = []
        with mf.open("r", encoding="utf-8", newline="") as f:
            for r in csv.DictReader(f):
                try: rows.append({"date": r["Date"], "close": float(r["Close"])})
                except: continue
        for i, r in enumerate(rows):
            prev1 = rows[i-1]["close"] if i >= 1 else None
            prev3 = rows[i-3]["close"] if i >= 3 else None
            trailing = [(rows[j]["close"] / rows[j-1]["close"]) - 1.0 for j in range(max(1, i-5), i+1)]
            ret1 = (r["close"] / prev1 - 1.0) if prev1 else 0.0
            ret3 = (r["close"] / prev3 - 1.0) if prev3 else 0.0
            mean = sum(trailing) / len(trailing) if trailing else 0.0
            vol  = math.sqrt(sum((v - mean)**2 for v in trailing) / len(trailing)) if trailing else 0.0
            context[(symbol, r["date"])] = {
                "market_prev_return_1d": ret1,
                "market_prev_return_3d": ret3,
                "market_volatility_5d":  vol,
                "market_momentum_5d":    mean,
            }
    return context


def build_vix_data(path: Path) -> dict:
    if not path.exists():
        return {}
    rows = []
    with path.open("r", encoding="utf-8", newline="") as f:
        for r in csv.DictReader(f):
            try:
                rows.append({"date": r["Date"], "close": float(r["Close"])})
            except: continue
    result = {}
    for i, r in enumerate(rows):
        prev = rows[i-1]["close"] if i >= 1 else r["close"]
        chg  = (r["close"] / prev - 1.0) if prev else 0.0
        result[r["date"]] = {"close": r["close"], "change_1d": chg}
    return result


def build_breadth_data(path: Path) -> dict:
    if not path.exists():
        return {}
    result = {}
    with path.open("r", encoding="utf-8", newline="") as f:
        for r in csv.DictReader(f):
            result[r["date"]] = {k: v for k, v in r.items() if k != "date"}
    return result


# ── Column selection (mirrors build_training_dataset.py) ──────────────────────

def should_keep(col: str) -> bool:
    return col in _ALL_ALLOWED


# ── Dual model loading ─────────────────────────────────────────────────────────

def _load_model_set(subdir: str) -> tuple[dict, dict] | tuple[None, None]:
    """Load lgbm/xgb/catboost + meta from MODEL_DIR/{subdir}/. Returns (models, meta) or (None, None)."""
    d = MODEL_DIR / subdir
    required = [d / "lgbm.joblib", d / "xgb.joblib", d / "catboost.joblib", d / "ensemble_meta.joblib"]
    if not all(p.exists() for p in required):
        return None, None
    mdls = {
        "lgbm":     joblib.load(d / "lgbm.joblib"),
        "xgb":      joblib.load(d / "xgb.joblib"),
        "catboost": joblib.load(d / "catboost.joblib"),
    }
    meta = joblib.load(d / "ensemble_meta.joblib")
    return mdls, meta


def _encode_row(row: pd.Series, train_df: pd.DataFrame, feature_cols: list[str]) -> np.ndarray:
    """One-hot encode a single inference row aligned to training feature space."""
    single   = pd.DataFrame([row.to_dict()])
    combined = pd.concat([train_df, single], ignore_index=True) if not train_df.empty else single
    for c in CATEGORICAL_COLUMNS:
        combined[c] = combined[c].astype("category")
    encoded  = pd.get_dummies(combined, columns=CATEGORICAL_COLUMNS, drop_first=False)
    pred_row = encoded.iloc[[-1]]
    for fc in feature_cols:
        if fc not in pred_row.columns:
            pred_row[fc] = 0
    return pred_row[feature_cols].values


# ── Prediction & MongoDB storage ───────────────────────────────────────────────

def predict_and_store(inference_df: pd.DataFrame, mongodb_uri: str, db_name: str) -> None:
    dir_models, dir_meta = _load_model_set("direction")
    vol_models, vol_meta = _load_model_set("volatility")

    if dir_models is None and vol_models is None:
        print("[predict] No models found. Run train_boosted_ensemble.py for both targets first.")
        print("  python ml/scripts/models/train_boosted_ensemble.py --target label_up_3d")
        print("  python ml/scripts/models/train_boosted_ensemble.py --target label_vol_high_5d")
        return

    # Use whichever feature_cols are available (both should be identical — same training CSV)
    feature_cols = (dir_meta or vol_meta)["feature_cols"]
    test_auc     = (dir_meta or vol_meta).get("test_auc", None)

    nlp_feats = [c for c in feature_cols if c in set(TENSION_COLS)]
    print(f"\n── Inference feature space ({len(feature_cols)} features) ──")
    print(f"  Direction target : label_up_3d   (model {'loaded' if dir_models else 'MISSING'})")
    print(f"  Volatility target: label_vol_high_5d (model {'loaded' if vol_models else 'MISSING'})")
    print(f"  NLP features ({len(nlp_feats)}): {nlp_feats}")
    print(f"  All features: {feature_cols}")
    print()

    # Load training data for one-hot encoding category space
    training_csv = WORKING / "gdelt_country_training_3d_market.csv"
    label_dtypes = {col: "Int64" for col in ALL_LABEL_COLUMNS}
    train_df = pd.read_csv(
        training_csv,
        dtype={"date": str, "country_code": str, "asset_symbol": str, **label_dtypes},
    ) if training_csv.exists() else pd.DataFrame()

    mapping = load_mapping()
    client  = MongoClient(mongodb_uri)
    db      = client[db_name]
    col     = db["ml_predictions"]

    col.create_index("iso2", unique=True)
    col.create_index("run_id")

    ops = []
    computed_at  = dt.datetime.now(dt.timezone.utc).isoformat()
    run_id       = computed_at
    written_iso2: list[str] = []

    latest_rows = (
        inference_df
        .sort_values("date")
        .groupby("country_code")
        .last()
        .reset_index()
    )

    for _, row in latest_rows.iterrows():
        gdelt_code = row["country_code"]
        meta_row   = mapping.get(gdelt_code)
        if not meta_row:
            continue

        iso2   = meta_row.get("iso2", gdelt_code)
        symbol = meta_row.get("asset_symbol", "")

        try:
            X = _encode_row(row, train_df, feature_cols)

            # ── Direction model (label_up_3d) ──────────────────────────────
            if dir_models:
                dir_prob  = float(np.mean([m.predict_proba(X)[0][1] for m in dir_models.values()]))
                # Keep "uncertain" only for the tightest band (±2pp around 0.50).
                # Outside that band always commit to a direction so the UI is useful.
                direction = (
                    "increase"  if dir_prob > 0.52 else
                    "decrease"  if dir_prob < 0.48 else
                    "uncertain"
                )
                direction_auc = dir_meta.get("test_auc") if dir_meta else None
            else:
                dir_prob, direction, direction_auc = None, None, None

            # ── Volatility model (label_vol_high_5d) ───────────────────────
            if vol_models:
                vol_prob  = float(np.mean([m.predict_proba(X)[0][1] for m in vol_models.values()]))
                vol_level = (
                    "high"    if vol_prob > 0.52 else
                    "low"     if vol_prob < 0.48 else
                    "neutral"
                )
                vol_auc = vol_meta.get("test_auc") if vol_meta else None
            else:
                vol_prob, vol_level, vol_auc = None, None, None

            # Risk level driven by volatility model when available
            if vol_prob is not None:
                risk_level = "HIGH" if vol_prob >= 0.60 else "MEDIUM" if vol_prob >= 0.42 else "LOW"
            elif dir_prob is not None:
                risk_level = "HIGH" if dir_prob >= 0.65 else "MEDIUM" if dir_prob >= 0.45 else "LOW"
            else:
                risk_level = "MEDIUM"

            doc = {
                "iso2":               iso2,
                "gdelt_country_code": gdelt_code,
                "country_name":       meta_row.get("country_name", ""),
                "asset_symbol":       symbol,
                # Direction signal (label_up_3d)
                "direction":          direction,
                "direction_prob":     round(dir_prob, 4) if dir_prob is not None else None,
                "direction_pct":      f"{round(dir_prob * 100)}%" if dir_prob is not None else None,
                "direction_auc":      round(direction_auc, 4) if direction_auc else None,
                # Volatility signal (label_vol_high_5d)
                "vol_level":          vol_level,
                "vol_prob":           round(vol_prob, 4) if vol_prob is not None else None,
                "vol_pct":            f"{round(vol_prob * 100)}%" if vol_prob is not None else None,
                "vol_auc":            round(vol_auc, 4) if vol_auc else None,
                # Combined
                "risk_level":         risk_level,
                # Legacy fields (backward compat)
                "vix_direction":      direction,
                "probability":        round(dir_prob, 4) if dir_prob is not None else None,
                "confidence_pct":     f"{round(dir_prob * 100)}%" if dir_prob is not None else None,
                "model_auc":          test_auc,
                "feature_date":       str(row.get("date", "")),
                "computed_at":        computed_at,
                "run_id":             run_id,
            }

            ops.append(UpdateOne({"iso2": iso2}, {"$set": doc}, upsert=True))
            written_iso2.append(iso2)
            dir_str = f"{direction} ({round(dir_prob * 100)}%)" if dir_prob is not None else "no-direction-model"
            vol_str = f"vol={vol_level}" if vol_level else "no-vol-model"
            print(f"  [{iso2}] {dir_str} · {vol_str}")

        except Exception as exc:
            print(f"  [{gdelt_code}] prediction failed: {exc}")

    if ops:
        result = col.bulk_write(ops)
        print(f"\n[mongo] Upserted {result.upserted_count} · Modified {result.modified_count} documents in ml_predictions")

        # Drop predictions for countries that fell out of this run's coverage.
        # Without this, stale rows from earlier runs would still serve via /trading.
        stale = col.delete_many({"iso2": {"$nin": written_iso2}})
        if stale.deleted_count:
            print(f"[mongo] Removed {stale.deleted_count} stale predictions not in current run")
    client.close()


# ── Main ───────────────────────────────────────────────────────────────────────

def main() -> int:
    # Read defaults from config/settings.py (which loads .env) so that
    # the Atlas URI is picked up automatically when --mongodb-uri is omitted.
    try:
        sys.path.insert(0, str(ROOT))
        from config.settings import settings as _cfg
        _default_uri = _cfg.MONGODB_URI
        _default_db  = _cfg.MONGODB_DB
    except Exception:
        _default_uri = "mongodb://localhost:27017"
        _default_db  = "geotrade"

    parser = argparse.ArgumentParser(description="Run full prediction pipeline and store in MongoDB.")
    parser.add_argument("--days-back", type=int, default=35,
                        help="Days of GDELT history to download (need ≥ 14 for rolling windows)")
    parser.add_argument("--mongodb-uri", default=_default_uri)
    parser.add_argument("--db-name",     default=_default_db)
    parser.add_argument("--skip-download", action="store_true",
                        help="Skip GDELT/market download (use existing files)")
    args = parser.parse_args()

    today      = dt.date.today()
    start_date = (today - dt.timedelta(days=args.days_back)).strftime("%Y-%m-%d")
    end_date   = today.strftime("%Y-%m-%d")

    PROCESSED.mkdir(parents=True, exist_ok=True)
    WORKING.mkdir(parents=True, exist_ok=True)
    MARKET_RAW.mkdir(parents=True, exist_ok=True)

    # ── Phase 1: Download & build features ────────────────────
    if not args.skip_download:
        print(f"\n=== Phase 1: Download GDELT {start_date} → {end_date} ===")
        run(SCRIPTS / "data" / "build_gdelt_country_daily_dataset.py",
            "--start-date", start_date, "--end-date", end_date,
            "--output-file", str(GDELT_DAILY_CSV))

        print("\n=== Rolling features ===")
        run(SCRIPTS / "features" / "build_country_rolling_features.py",
            "--input-file",  str(GDELT_DAILY_CSV),
            "--output-file", str(ROLLING_CSV))

        print("\n=== Market data ===")
        run(SCRIPTS / "data" / "download_market_data.py",
            "--mapping-file", str(MAPPING_CSV),
            "--output-dir",   str(MARKET_RAW),
            "--start-date",   start_date,
            "--end-date",     end_date)

        print("\n=== VIX ===")
        run(SCRIPTS / "data" / "download_global_vol_indices.py",
            "--output-dir",  str(MARKET_RAW),
            "--start-date",  start_date,
            "--end-date",    end_date)

        print("\n=== Breadth features ===")
        run(SCRIPTS / "features" / "build_breadth_features.py",
            "--input-file",  str(GDELT_DAILY_CSV),
            "--output-file", str(BREADTH_CSV))
    else:
        print("[skip-download] Using existing files")
        if not ROLLING_CSV.exists():
            print(f"ERROR: {ROLLING_CSV} not found. Run without --skip-download first.")
            return 1

    # ── Phase 2: Build inference rows (no labels needed) ──────
    print("\n=== Phase 2: Build inference feature rows ===")

    mapping      = load_mapping()
    market_ctx   = build_market_context(MARKET_RAW)
    vix_data     = build_vix_data(MARKET_RAW / "VIX.csv")
    breadth_data = build_breadth_data(BREADTH_CSV)

    # Load latest NLP tension signals per country from MongoDB
    from pymongo import MongoClient as _MongoClient
    _mongo_client   = _MongoClient(args.mongodb_uri)
    _tension_db     = _mongo_client[args.db_name]
    tension_signals = load_tension_signals(_tension_db)
    _mongo_client.close()

    # Find most recent trading date for each asset
    asset_dates: dict[str, tuple[list, list]] = {}
    for gdelt_code, meta_row in mapping.items():
        symbol = meta_row["asset_symbol"]
        market_path = MARKET_RAW / f"{symbol.replace('.', '_')}.csv"
        if market_path.exists():
            asset_dates[gdelt_code] = load_market_series(market_path)

    inference_rows = []
    with ROLLING_CSV.open("r", encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        # Group last 2 rows per country (need lag for delta features)
        by_country: dict[str, list] = defaultdict(list)
        for row in reader:
            by_country[row["country_code"]].append(row)

    for gdelt_code, rows in by_country.items():
        meta_row = mapping.get(gdelt_code)
        if not meta_row:
            continue

        # Take the latest row
        latest = rows[-1]
        feature_date_str = latest["date"]
        try:
            feature_date = dt.datetime.strptime(feature_date_str, "%Y%m%d").date()
        except ValueError:
            continue

        # Find reference market date (most recent trading day ≤ feature date)
        symbol = meta_row["asset_symbol"]
        trading_dates, closes = asset_dates.get(gdelt_code, ([], []))
        if not trading_dates:
            ref_date_str = ""
        else:
            ref_idx = bisect.bisect_right(trading_dates, feature_date) - 1
            ref_date_str = trading_dates[ref_idx].strftime("%Y-%m-%d") if ref_idx >= 0 else ""

        # Add asset info
        latest["asset_symbol"] = symbol
        latest["asset_name"]   = meta_row.get("asset_name", "")
        latest["asset_type"]   = meta_row.get("asset_type", "")

        # Skip if no actual news data for this country
        try:
            doc_count = float(latest.get("document_count", 0) or 0)
        except (ValueError, TypeError):
            doc_count = 0.0
        if doc_count == 0:
            print(f"  [{gdelt_code}] skipped — no GDELT news data in window")
            continue

        # Engineer derived features
        latest = engineer_row(latest)

        # Add market context
        latest = add_market_context(latest, symbol, ref_date_str,
                                    market_ctx, vix_data, breadth_data)

        # Add NLP tension signals — join by iso2 using most recent available signal
        iso2 = meta_row.get("iso2", gdelt_code)
        tension_feats = tension_signals.get(iso2.upper())
        if tension_feats:
            latest.update(tension_feats)
            latest["has_tension_data"] = 1
        else:
            latest.update(TENSION_DEFAULTS)

        # Drop columns not in training feature set
        filtered = {k: v for k, v in latest.items() if should_keep(k)}
        inference_rows.append(filtered)

    if not inference_rows:
        print("ERROR: No inference rows built. Check GDELT download and mapping.")
        return 1

    inference_df = pd.DataFrame(inference_rows)
    inference_df.to_csv(INFERENCE_CSV, index=False)
    print(f"Inference rows: {len(inference_df)} across {inference_df['country_code'].nunique()} countries")
    print(f"Saved to: {INFERENCE_CSV}")

    # ── Phase 3: Predict & store ───────────────────────────────
    print("\n=== Phase 3: Predict & store in MongoDB ===")
    predict_and_store(inference_df, args.mongodb_uri, args.db_name)

    print("\nDone. Predictions stored in MongoDB collection: ml_predictions")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
