"""
pipeline/modeling/train.py
───────────────────────────
Trains RandomForest and LightGBM classifiers.
Returns a results dict consumed by plots.py and the run script.

v2 improvement: save_best_model() persists the best-performing model
to disk (data/models/) so it can be loaded by the API without retraining.
"""

import joblib
import numpy as np
from pathlib import Path
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import accuracy_score, f1_score, roc_auc_score
import lightgbm as lgb

# Model output directory
_MODEL_DIR = Path(__file__).resolve().parent.parent.parent / "data" / "models"


def _metrics(y_true, y_pred, y_prob) -> dict:
    return {
        "accuracy": round(accuracy_score(y_true, y_pred), 4),
        "f1":       round(f1_score(y_true, y_pred, zero_division=0), 4),
        "roc_auc":  round(roc_auc_score(y_true, y_prob), 4),
        "y_pred":   y_pred,
        "y_prob":   y_prob,
    }


def train_random_forest(X_train, y_train, X_test, y_test,
                        feature_names: list[str]) -> dict:
    model = RandomForestClassifier(
        n_estimators=200,
        max_depth=6,
        random_state=42,
        class_weight="balanced",
        n_jobs=-1,
    )
    model.fit(X_train, y_train)
    y_pred = model.predict(X_test)
    y_prob = model.predict_proba(X_test)[:, 1]

    return {
        "name":         "RandomForest",
        "model":        model,
        "features":     feature_names,
        "importances":  model.feature_importances_,
        **_metrics(y_test, y_pred, y_prob),
    }


def train_lightgbm(X_train, y_train, X_test, y_test,
                   feature_names: list[str]) -> dict:
    model = lgb.LGBMClassifier(
        n_estimators=300,
        max_depth=5,
        learning_rate=0.05,
        random_state=42,
        class_weight="balanced",
        verbose=-1,
    )
    model.fit(X_train, y_train, eval_set=[(X_test, y_test)])
    y_pred = model.predict(X_test)
    y_prob = model.predict_proba(X_test)[:, 1]

    return {
        "name":        "LightGBM",
        "model":       model,
        "features":    feature_names,
        "importances": model.feature_importances_,
        **_metrics(y_test, y_pred, y_prob),
    }


def save_best_model(results: list[dict]) -> Path:
    """
    Pick the best model by ROC-AUC and save it to data/models/best_model.joblib.
    Also saves metadata (feature names, model name, AUC) alongside.

    Called at the end of step4_model.py so the API can load it without retraining.

    Returns the path to the saved model file.
    """
    best = max(results, key=lambda r: r["roc_auc"])
    _MODEL_DIR.mkdir(parents=True, exist_ok=True)

    model_path = _MODEL_DIR / "best_model.joblib"
    meta_path  = _MODEL_DIR / "best_model_meta.joblib"

    joblib.dump(best["model"], model_path)
    joblib.dump({
        "name":     best["name"],
        "features": best["features"],
        "roc_auc":  best["roc_auc"],
        "accuracy": best["accuracy"],
        "f1":       best["f1"],
    }, meta_path)

    print(f"  [model] Saved {best['name']} (AUC={best['roc_auc']}) → {model_path}")
    return model_path


def load_best_model():
    """
    Load the saved best model and its metadata.
    Returns (model, meta_dict) or (None, None) if not found.
    """
    model_path = _MODEL_DIR / "best_model.joblib"
    meta_path  = _MODEL_DIR / "best_model_meta.joblib"

    if not model_path.exists():
        return None, None
    try:
        model = joblib.load(model_path)
        meta  = joblib.load(meta_path) if meta_path.exists() else {}
        return model, meta
    except Exception as e:
        print(f"  [model] Failed to load saved model: {e}")
        return None, None
