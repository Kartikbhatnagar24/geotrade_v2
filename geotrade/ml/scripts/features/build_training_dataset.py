#!/usr/bin/env python3
"""
Create a training-ready subset from the engineered labeled dataset.

Optionally joins MongoDB daily_signals to enrich each row with NLP-derived
tension features (tension_score, smoothed_score, avg_neg_sentiment,
conflict_gravity, nlp_event_count).  These are the features produced by the
BART+DistilBERT NLP pipeline (steps 1-3) and are a richer signal than the
raw GDELT document-count / avg_tone features.

Join key: (iso2, YYYY-MM-DD).  GDELT dates are YYYYMMDD — converted inline.
Country mapping: config/country_asset_mapping.csv (gdelt_code → iso2).

Usage (with tension join):
    python ml/scripts/features/build_training_dataset.py \
        --mongodb-uri mongodb+srv://... \
        --db-name geotrade

Usage (plain CSV filter, no MongoDB):
    python ml/scripts/features/build_training_dataset.py
"""

from __future__ import annotations

import argparse
import csv
import datetime as dt
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
MAPPING_CSV = ROOT / "config" / "country_asset_mapping.csv"

# Load defaults from .env via config/settings.py (same pattern as run_predict.py)
try:
    import sys as _sys
    _sys.path.insert(0, str(ROOT))
    from config.settings import settings as _cfg
    _DEFAULT_URI    = _cfg.MONGODB_URI
    _DEFAULT_DB     = _cfg.MONGODB_DB
except Exception:
    _DEFAULT_URI    = "mongodb://localhost:27017"
    _DEFAULT_DB     = "geotrade"

# ── Thesis feature set (Section 4.3, f1–f30) ─────────────────────────────────
#
# 25 GDELT/market base features (f1–f25) mapped to column names that exist in
# the engineered CSV, plus 5 NLP features (f26–f30) from daily_signals.
# has_tension_data is a helper flag (not counted in the 30) that marks whether
# the NLP values are real BART output (1) or neutral defaults (0).
#
# f1  global_tension           → avg_tone_mean_mean_14d
# f2  max_tension              → tone_range_14d
# f3  weighted_tension         → breadth_high_news_frac
# f4  n_high_tension_countries → breadth_countries_active
# f5  tension_concentration    → breadth_neg_tone_frac
# f6  tension_velocity_7d      → avg_tone_mean_3d_minus_14d
# f7  tension_velocity_3d      → document_count_3d_vs_14d
# f8  tension_lag_1d           → theme_mentions_3d_vs_14d
# f9  tension_lag_7d           → cameo_event_mentions_3d_vs_14d
# f10 news_type_conflict       → document_count_sum_14d
# f11 news_type_military       → cameo_event_mentions_sum_14d
# f12 news_type_sanctions      → theme_density_14d
# f13 news_type_economic       → news_intensity_14d
# f14 conflict_intensity       → cameo_event_mentions_vs_14d
# f15 vix_level                → vix_close
# f16 vix_pct_change           → vix_change_1d
# f17 vix_7d_ma                → market_volatility_5d
# f18 vix_above_20             → market_momentum_5d
# f19 vix_above_30             → market_prev_return_1d
# f20 sp500_volatility_5d      → market_prev_return_3d
# f21 market_regime            → document_count_vs_14d
# f22 tension_regime_num       → source_diversity_ratio
# f23 days_in_current_regime   → person_diversity_ratio
# f24 tension_x_vix            → tone_range
# f25 high_tension_stressed    → person_mentions_3d_vs_14d
# f26 tension_score            → tension_score
# f27 smoothed_score           → smoothed_score
# f28 avg_neg_sentiment        → avg_neg_sentiment
# f29 conflict_gravity         → conflict_gravity
# f30 nlp_event_count          → nlp_event_count

THESIS_BASE_FEATURES: set[str] = {
    # Tension-Level (f1–f5)
    "avg_tone_mean_mean_14d",
    "tone_range_14d",
    "breadth_high_news_frac",
    "breadth_countries_active",
    "breadth_neg_tone_frac",
    # Velocity/Momentum (f6–f9)
    "avg_tone_mean_3d_minus_14d",
    "document_count_3d_vs_14d",
    "theme_mentions_3d_vs_14d",
    "cameo_event_mentions_3d_vs_14d",
    # News Composition (f10–f14)
    "document_count_sum_14d",
    "cameo_event_mentions_sum_14d",
    "theme_density_14d",
    "news_intensity_14d",
    "cameo_event_mentions_vs_14d",
    # Market Condition (f15–f20)
    "vix_close",
    "vix_change_1d",
    "market_volatility_5d",
    "market_momentum_5d",
    "market_prev_return_1d",
    "market_prev_return_3d",
    # Regime / Interaction (f21–f25)
    "document_count_vs_14d",
    "source_diversity_ratio",
    "person_diversity_ratio",
    "tone_range",
    "person_mentions_3d_vs_14d",
}

# NLP tension features (f26–f30) — joined from MongoDB daily_signals
TENSION_COLS: list[str] = [
    "tension_score",       # f26: composite NLP tension score [0,1]
    "smoothed_score",      # f27: reliability-smoothed score [0,1]
    "avg_neg_sentiment",   # f28: fraction of negatively-classified articles
    "conflict_gravity",    # f29: Goldstein-weighted event-type gravity
    "nlp_event_count",     # f30: articles processed by NLP pipeline
    "has_tension_data",    # helper flag: 1 = real BART output, 0 = default
]

TENSION_DEFAULTS: dict[str, float | int] = {
    "tension_score":     0.5,
    "smoothed_score":    0.5,
    "avg_neg_sentiment": 0.0,
    "conflict_gravity":  0.0,
    "nlp_event_count":   0,
    "has_tension_data":  0,
}

KEEP_META: set[str] = {
    "date",
    "country_code",
    "asset_symbol",
    "label_up_3d",
    "label_vol_high_5d",
    "label_has_market_data",
}

# All allowed columns = meta + 25 base + 6 NLP (5 thesis + has_tension_data)
_ALL_ALLOWED: set[str] = KEEP_META | THESIS_BASE_FEATURES | set(TENSION_COLS)


def parse_date(value: str) -> dt.date:
    return dt.datetime.strptime(value, "%Y%m%d").date()


def gdelt_date_to_iso(value: str) -> str:
    """Convert YYYYMMDD → YYYY-MM-DD for MongoDB date key lookup."""
    if len(value) == 8:
        return f"{value[:4]}-{value[4:6]}-{value[6:]}"
    return value


def should_keep_column(name: str) -> bool:
    return name in _ALL_ALLOWED


# ── MongoDB tension loader ────────────────────────────────────────────────────

def load_mapping(path: Path) -> dict[str, str]:
    """Returns {gdelt_country_code: iso2}."""
    mapping: dict[str, str] = {}
    with path.open("r", encoding="utf-8", newline="") as f:
        for row in csv.DictReader(f):
            if row.get("enabled", "1") == "1":
                mapping[row["gdelt_country_code"]] = row["iso2"]
    return mapping



def load_tension_lookup(uri: str, db_name: str) -> dict[tuple[str, str], dict]:
    """
    Fetch daily_signals + per-type article fractions from processed_events.
    Returns {(iso2_upper, 'YYYY-MM-DD'): {tension + type-frac feature dict}}.

    Loads only the 5 thesis NLP features (f26–f30) from daily_signals.
    Returns {(iso2_upper, 'YYYY-MM-DD'): {tension feature dict}}.
    """
    try:
        from pymongo import MongoClient
    except ImportError:
        print("[tension] pymongo not installed — skipping tension join")
        return {}

    print(f"[tension] Connecting to MongoDB: {uri[:40]}...")
    client = MongoClient(uri, serverSelectionTimeoutMS=8_000)
    try:
        db = client[db_name]
        signal_docs = list(db["daily_signals"].find(
            {},
            {"_id": 0, "iso": 1, "date": 1,
             "tension_score": 1, "smoothed_score": 1,
             "avg_neg_sentiment": 1, "conflict_gravity": 1, "event_count": 1},
        ))
    finally:
        client.close()

    lookup: dict[tuple[str, str], dict] = {}
    for doc in signal_docs:
        iso  = str(doc.get("iso", "")).upper()
        date = str(doc.get("date", ""))
        if not iso or not date:
            continue
        lookup[(iso, date)] = {
            "tension_score":     float(doc.get("tension_score",     TENSION_DEFAULTS["tension_score"])),
            "smoothed_score":    float(doc.get("smoothed_score",    TENSION_DEFAULTS["smoothed_score"])),
            "avg_neg_sentiment": float(doc.get("avg_neg_sentiment", TENSION_DEFAULTS["avg_neg_sentiment"])),
            "conflict_gravity":  float(doc.get("conflict_gravity",  TENSION_DEFAULTS["conflict_gravity"])),
            "nlp_event_count":   int(doc.get("event_count",         TENSION_DEFAULTS["nlp_event_count"])),
        }

    print(f"[tension] {len(lookup):,} (iso2, date) signals loaded from daily_signals")
    return lookup


# ── Main ──────────────────────────────────────────────────────────────────────

def main() -> int:
    parser = argparse.ArgumentParser(
        description="Build a filtered training dataset from engineered features, "
                    "optionally enriched with NLP tension signals from MongoDB."
    )
    parser.add_argument(
        "--input-file",
        default="ml/data/working/gdelt_country_labeled_2y_engineered.csv",
    )
    parser.add_argument(
        "--output-file",
        default="ml/data/working/gdelt_country_training_3d.csv",
    )
    parser.add_argument(
        "--min-date",
        default="2024-05-15",
        help="Exclude warm-up rows before this YYYY-MM-DD date",
    )
    parser.add_argument(
        "--mongodb-uri",
        default=_DEFAULT_URI,
        help="MongoDB connection string (defaults to MONGODB_URI in .env).",
    )
    parser.add_argument(
        "--db-name",
        default=_DEFAULT_DB,
        help="MongoDB database name (defaults to MONGODB_DB in .env).",
    )
    parser.add_argument(
        "--mapping-file",
        default=str(MAPPING_CSV),
        help="CSV mapping GDELT country codes to ISO2 (for tension join).",
    )
    args = parser.parse_args()

    min_date   = dt.datetime.strptime(args.min_date, "%Y-%m-%d").date()
    input_path = Path(args.input_file)
    output_path = Path(args.output_file)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    # ── Tension join setup ────────────────────────────────────────
    tension_lookup: dict[tuple[str, str], dict] = {}
    gdelt_to_iso2: dict[str, str] = {}
    if args.mongodb_uri:
        gdelt_to_iso2  = load_mapping(Path(args.mapping_file))
        tension_lookup = load_tension_lookup(args.mongodb_uri, args.db_name)

    with input_path.open("r", encoding="utf-8", newline="") as fin:
        reader = csv.DictReader(fin)
        base_columns = list(reader.fieldnames or [])

        # Tension columns are appended after the base feature set
        all_columns   = base_columns + [c for c in TENSION_COLS if c not in base_columns]
        kept_columns  = [name for name in all_columns if should_keep_column(name)]

        feature_cols = [c for c in kept_columns if c not in KEEP_META]
        print(f"\n--- Training columns ({len(kept_columns)} total, {len(feature_cols)} features) ---")
        for i, col in enumerate(kept_columns, 1):
            tag = " [TARGET]" if col in {"label_up_3d", "label_vol_high_5d"} else \
                  " [META]"   if col in KEEP_META else \
                  " [NLP]"    if col in TENSION_COLS else ""
            print(f"  {i:>3}. {col}{tag}")
        print()

        with output_path.open("w", encoding="utf-8", newline="") as fout:
            writer = csv.DictWriter(fout, fieldnames=kept_columns)
            writer.writeheader()

            kept_rows    = 0
            joined_rows  = 0
            missing_rows = 0

            for row in reader:
                if row.get("label_has_market_data") != "1":
                    continue
                if row.get("label_up_3d", "") == "" or row.get("label_vol_high_5d", "") == "":
                    continue
                if parse_date(row["date"]) < min_date:
                    continue

                # ── Tension feature join ──────────────────────────
                if tension_lookup:
                    gdelt_code = row.get("country_code", "")
                    iso2       = gdelt_to_iso2.get(gdelt_code, "")
                    date_str   = gdelt_date_to_iso(row.get("date", ""))
                    tension_feats = tension_lookup.get((iso2.upper(), date_str))
                    if tension_feats:
                        row.update(tension_feats)
                        row["has_tension_data"] = 1
                        joined_rows += 1
                    else:
                        row.update(TENSION_DEFAULTS)  # has_tension_data=0 already in defaults
                        missing_rows += 1
                else:
                    row.update(TENSION_DEFAULTS)

                writer.writerow({col: row.get(col, "") for col in kept_columns})
                kept_rows += 1

    print(f"Input:            {input_path.resolve()}")
    print(f"Output:           {output_path.resolve()}")
    print(f"Selected columns: {len(kept_columns)}")
    print(f"Kept rows:        {kept_rows}")
    if tension_lookup:
        hit_rate = joined_rows / max(kept_rows, 1) * 100
        print(f"Tension join:     {joined_rows} hits / {missing_rows} misses ({hit_rate:.1f}% hit rate)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
