#!/usr/bin/env python3
"""
Train LightGBM, XGBoost, CatBoost, and a simple ensemble on the training dataset.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import joblib

import lightgbm as lgb
import numpy as np
import pandas as pd
from catboost import CatBoostClassifier
from lightgbm import LGBMClassifier
from sklearn.metrics import (
    accuracy_score, brier_score_loss, f1_score, log_loss,
    precision_score, recall_score, roc_auc_score,
)
from xgboost import XGBClassifier


ALL_LABEL_COLUMNS = ["label_up_3d", "label_vol_high_5d", "label_has_market_data"]
META_COLUMNS = ["date", "country_code", "asset_symbol"] + ALL_LABEL_COLUMNS
CATEGORICAL_COLUMNS = ["country_code", "asset_symbol"]


def load_splits(path: Path, target_col: str):
    label_dtypes = {col: int for col in ALL_LABEL_COLUMNS}
    df = pd.read_csv(
        path,
        dtype={"date": str, "country_code": str, "asset_symbol": str, **label_dtypes},
    )
    # Drop rows where the chosen target is missing
    df = df[df[target_col].notna()].copy()
    dates = sorted(df["date"].unique().tolist())
    train_cut = int(len(dates) * 0.70)
    valid_cut = int(len(dates) * 0.85)
    train_dates = set(dates[:train_cut])
    valid_dates = set(dates[train_cut:valid_cut])
    test_dates = set(dates[valid_cut:])

    train_df = df[df["date"].isin(train_dates)].copy()
    valid_df = df[df["date"].isin(valid_dates)].copy()
    test_df = df[df["date"].isin(test_dates)].copy()
    return train_df, valid_df, test_df


def encode_frames(train_df: pd.DataFrame, valid_df: pd.DataFrame, test_df: pd.DataFrame, target_col: str):
    frames = [train_df, valid_df, test_df]
    combined = pd.concat(frames, axis=0, ignore_index=True)
    for col in CATEGORICAL_COLUMNS:
        combined[col] = combined[col].astype("category")
    encoded = pd.get_dummies(combined, columns=CATEGORICAL_COLUMNS, drop_first=False)

    train_end = len(train_df)
    valid_end = train_end + len(valid_df)
    train_encoded = encoded.iloc[:train_end].copy()
    valid_encoded = encoded.iloc[train_end:valid_end].copy()
    test_encoded = encoded.iloc[valid_end:].copy()

    feature_cols = [col for col in train_encoded.columns if col not in META_COLUMNS]
    X_train = train_encoded[feature_cols]
    y_train = train_encoded[target_col]
    X_valid = valid_encoded[feature_cols]
    y_valid = valid_encoded[target_col]
    X_test = test_encoded[feature_cols]
    y_test = test_encoded[target_col]
    return X_train, y_train, X_valid, y_valid, X_test, y_test, feature_cols


def metrics_from_probs(y_true, probs):
    preds = (probs >= 0.5).astype(int)
    return {
        "rows": int(len(y_true)),
        "accuracy": round(float(accuracy_score(y_true, preds)), 6),
        "precision": round(float(precision_score(y_true, preds, zero_division=0)), 6),
        "recall": round(float(recall_score(y_true, preds, zero_division=0)), 6),
        "f1": round(float(f1_score(y_true, preds, zero_division=0)), 6),
        "auc": round(float(roc_auc_score(y_true, probs)), 6),
        "logloss": round(float(log_loss(y_true, probs, labels=[0, 1])), 6),
        # Brier score: lower = better-calibrated probabilities. 0 = perfect.
        "brier": round(float(brier_score_loss(y_true, probs)), 6),
        "positive_rate": round(float(np.mean(y_true)), 6),
    }


def top_importances(model, feature_names, limit=20):
    if hasattr(model, "feature_importances_"):
        importances = model.feature_importances_
    else:
        return []
    pairs = sorted(zip(feature_names, importances), key=lambda item: item[1], reverse=True)[:limit]
    return [{"feature": name, "importance": round(float(score), 6)} for name, score in pairs]


def main() -> int:
    parser = argparse.ArgumentParser(description="Train boosted tree models and a simple ensemble.")
    parser.add_argument("--input-file", default="ml/data/working/gdelt_country_training_3d_market.csv")
    parser.add_argument("--metrics-file", default="ml/data/working/boosted_ensemble_metrics.json")
    parser.add_argument("--model-dir", default="ml/data/models", help="Parent directory for model subdirs (direction/ or volatility/ appended automatically)")
    parser.add_argument(
        "--target",
        choices=["label_up_3d", "label_vol_high_5d"],
        default="label_up_3d",
        help="Which label column to train on",
    )
    parser.add_argument(
        "--market-only",
        action="store_true",
        help="Use only the 4 market context features (ablation: no GDELT)",
    )
    args = parser.parse_args()

    MARKET_FEATURES = {"market_volatility_5d", "market_momentum_5d", "market_prev_return_1d", "market_prev_return_3d", "vix_close", "vix_change_1d"}

    train_df, valid_df, test_df = load_splits(Path(args.input_file), args.target)
    X_train, y_train, X_valid, y_valid, X_test, y_test, feature_cols = encode_frames(
        train_df, valid_df, test_df, args.target
    )

    if args.market_only:
        keep = [c for c in feature_cols if c in MARKET_FEATURES]
        X_train, X_valid, X_test = X_train[keep], X_valid[keep], X_test[keep]
        feature_cols = keep

    EARLY_STOPPING_ROUNDS = 50

    models = {
        "lightgbm": LGBMClassifier(
            n_estimators=1000,
            learning_rate=0.05,
            num_leaves=31,
            subsample=0.8,
            colsample_bytree=0.8,
            random_state=42,
        ),
        "xgboost": XGBClassifier(
            n_estimators=1000,
            learning_rate=0.05,
            max_depth=6,
            subsample=0.8,
            colsample_bytree=0.8,
            eval_metric="auc",
            early_stopping_rounds=EARLY_STOPPING_ROUNDS,
            random_state=42,
            n_jobs=4,
        ),
        "catboost": CatBoostClassifier(
            iterations=1000,
            learning_rate=0.05,
            depth=6,
            loss_function="Logloss",
            eval_metric="AUC",
            early_stopping_rounds=EARLY_STOPPING_ROUNDS,
            verbose=False,
            random_seed=42,
        ),
    }

    results: dict[str, object] = {}
    valid_probs = {}
    test_probs = {}

    for name, model in models.items():
        if name == "lightgbm":
            model.fit(
                X_train, y_train,
                eval_set=[(X_valid, y_valid)],
                callbacks=[
                    lgb.early_stopping(EARLY_STOPPING_ROUNDS, verbose=False),
                    lgb.log_evaluation(period=-1),
                ],
            )
            best_iter = int(model.best_iteration_)
        elif name == "xgboost":
            model.fit(
                X_train, y_train,
                eval_set=[(X_valid, y_valid)],
                verbose=False,
            )
            best_iter = int(model.best_iteration)
        else:  # catboost
            model.fit(X_train, y_train, eval_set=(X_valid, y_valid))
            best_iter = int(model.best_iteration_)

        train_prob = model.predict_proba(X_train)[:, 1]
        valid_prob = model.predict_proba(X_valid)[:, 1]
        test_prob = model.predict_proba(X_test)[:, 1]
        valid_probs[name] = valid_prob
        test_probs[name] = test_prob
        results[name] = {
            "best_iteration": best_iter,
            "train": metrics_from_probs(y_train, train_prob),
            "validation": metrics_from_probs(y_valid, valid_prob),
            "test": metrics_from_probs(y_test, test_prob),
            "top_feature_importances": top_importances(model, feature_cols),
        }

    ensemble_valid = np.mean(np.column_stack([valid_probs[name] for name in models]), axis=1)
    ensemble_test = np.mean(np.column_stack([test_probs[name] for name in models]), axis=1)
    ensemble_train = np.mean(
        np.column_stack([models[name].predict_proba(X_train)[:, 1] for name in models]),
        axis=1,
    )
    results["ensemble_mean"] = {
        "train": metrics_from_probs(y_train, ensemble_train),
        "validation": metrics_from_probs(y_valid, ensemble_valid),
        "test": metrics_from_probs(y_test, ensemble_test),
    }
    results["split"] = {
        "target": args.target,
        "train_rows": int(len(train_df)),
        "validation_rows": int(len(valid_df)),
        "test_rows": int(len(test_df)),
        "train_start": str(train_df["date"].iloc[0]) if len(train_df) else "",
        "train_end": str(train_df["date"].iloc[-1]) if len(train_df) else "",
        "validation_start": str(valid_df["date"].iloc[0]) if len(valid_df) else "",
        "validation_end": str(valid_df["date"].iloc[-1]) if len(valid_df) else "",
        "test_start": str(test_df["date"].iloc[0]) if len(test_df) else "",
        "test_end": str(test_df["date"].iloc[-1]) if len(test_df) else "",
    }

    # Save trained models to a target-specific subdirectory
    # label_up_3d       → {model_dir}/direction/
    # label_vol_high_5d → {model_dir}/volatility/
    _SUBDIR = {"label_up_3d": "direction", "label_vol_high_5d": "volatility"}
    subdir = _SUBDIR.get(args.target, args.target)
    model_dir = Path(args.model_dir) / subdir
    model_dir.mkdir(parents=True, exist_ok=True)
    joblib.dump(models["lightgbm"], model_dir / "lgbm.joblib")
    joblib.dump(models["xgboost"], model_dir / "xgb.joblib")
    joblib.dump(models["catboost"], model_dir / "catboost.joblib")
    joblib.dump(
        {
            "feature_cols": feature_cols,
            "target":       args.target,
            "test_auc":     results["ensemble_mean"]["test"]["auc"],
            "test_brier":   results["ensemble_mean"]["test"]["brier"],
        },
        model_dir / "ensemble_meta.joblib",
    )
    print(f"Models saved to {model_dir.resolve()}")

    # If the user left the default metrics filename, suffix it with the target name
    metrics_file = args.metrics_file
    if metrics_file == "ml/data/working/boosted_ensemble_metrics.json":
        suffix = f"{args.target}_market_only" if args.market_only else args.target
        metrics_file = f"ml/data/working/boosted_ensemble_metrics_{suffix}.json"
    metrics_path = Path(metrics_file)
    metrics_path.parent.mkdir(parents=True, exist_ok=True)
    metrics_path.write_text(json.dumps(results, indent=2), encoding="utf-8")
    print(json.dumps(results, indent=2))
    print(f"Metrics written to {metrics_path.resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

