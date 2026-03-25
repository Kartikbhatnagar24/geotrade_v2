"""
pipeline/modeling/train.py
───────────────────────────
Trains RandomForest and LightGBM classifiers.
Returns a results dict consumed by plots.py and the run script.
"""

import numpy as np
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import accuracy_score, f1_score, roc_auc_score
import lightgbm as lgb


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
