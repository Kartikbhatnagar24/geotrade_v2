"""
scripts/step4_model.py — Market Modeling
==========================================
Downloads VIX + S&P500 via yfinance.
Merges with daily tension signals.
Trains RandomForest + LightGBM.
Saves evaluation metrics and 4 plots to data/plots/

Run (from project root):
    python scripts/step4_model.py
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pandas as pd

from config.settings import settings
from pipeline.utils.logger import StepLogger
from pipeline.modeling.features import (
    load_tension_df, download_market_df, synthetic_market_df,
    build_merged, split_features,
)
from pipeline.modeling.train import train_random_forest, train_lightgbm
from pipeline.modeling.plots import (
    plot_tension_vs_volatility, plot_feature_importance,
    plot_roc_curves, plot_model_comparison,
)

log = StepLogger("Step 4 — Market Modeling")


def main():
    log.header()

    # ── 1. Tension signals ─────────────────────────────────────
    log.section("Load tension signals")
    tension_df = load_tension_df()
    log.success(f"{len(tension_df)} daily global signals")
    log.info(f"Date range: {tension_df['date'].min().date()} → {tension_df['date'].max().date()}")

    # ── 2. Market data ─────────────────────────────────────────
    log.section("Download market data (yfinance)")
    start = (tension_df["date"].min() - pd.Timedelta(days=10)).strftime("%Y-%m-%d")
    end   = (tension_df["date"].max() + pd.Timedelta(days=5)).strftime("%Y-%m-%d")

    try:
        market_df = download_market_df(start, end)
        log.success(f"{len(market_df)} market rows downloaded")
    except Exception as e:
        log.warn(f"yfinance failed ({e}) — using synthetic data for development")
        market_df = synthetic_market_df(tension_df)
        log.info(f"{len(market_df)} synthetic rows generated")

    # ── 3. Merge + features ────────────────────────────────────
    log.section("Build feature matrix")
    merged = build_merged(tension_df, market_df)
    csv_path = settings.DATA_PROCESSED / "merged_dataset.csv"
    csv_path.parent.mkdir(parents=True, exist_ok=True)
    merged.to_csv(csv_path, index=False)
    log.success(f"{len(merged)} rows merged → {csv_path}")

    if len(merged) < 20:
        log.warn("Very few data points — results may not be meaningful.")
        log.warn("Set INGESTION_DAYS_BACK=90 in .env and re-run steps 1-3.")

    X_train, X_test, y_train, y_test, feat_cols = split_features(merged)
    log.info(f"Train: {len(X_train)}  Test: {len(X_test)}  "
             f"Features: {len(feat_cols)}  "
             f"Positive rate: {y_test.mean():.1%}")

    # ── 4. Train models ────────────────────────────────────────
    log.section("Training")
    rf_result   = train_random_forest(X_train, y_train, X_test, y_test, feat_cols)
    lgbm_result = train_lightgbm(X_train, y_train, X_test, y_test, feat_cols)
    results     = [rf_result, lgbm_result]

    # ── 5. Generate plots ──────────────────────────────────────
    log.section("Generating plots")
    plots = []
    plots.append(plot_tension_vs_volatility(merged))
    for r in results:
        plots.append(plot_feature_importance(r))
    plots.append(plot_roc_curves(results, y_test))
    plots.append(plot_model_comparison(results))
    for p in plots:
        log.info(f"Saved → {p}")

    # ── Summary ────────────────────────────────────────────────
    log.footer({
        "RandomForest  Acc/F1/AUC": f"{rf_result['accuracy']} / {rf_result['f1']} / {rf_result['roc_auc']}",
        "LightGBM      Acc/F1/AUC": f"{lgbm_result['accuracy']} / {lgbm_result['f1']} / {lgbm_result['roc_auc']}",
        "Plots saved to":            str(settings.DATA_PLOTS),
        "Next step":                 "cd backend  →  uvicorn main:app --reload",
    })


if __name__ == "__main__":
    main()
