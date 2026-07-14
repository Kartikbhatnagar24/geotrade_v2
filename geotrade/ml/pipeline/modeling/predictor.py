"""
Ensemble predictor — reads from the ml_predictions collection.

The collection is the single source of truth: it is rewritten end-to-end by
ml/scripts/models/run_predict.py, which also prunes stale rows. We deliberately
do NOT fall back to the training CSV here — serving features from historical
training rows would produce a "prediction" that does not reflect the current
GDELT window, and the UI would have no way to know.

If the requested country is missing or its row has gone stale, return
used_ml=False with a plain-English reason so the caller can surface the gap
instead of silently rendering a heuristic value as if it were a model output.

Workflow:
  1. Train   : python ml/scripts/models/train_boosted_ensemble.py
  2. Predict : python ml/scripts/models/run_predict.py     (writes ml_predictions)
  3. Serve   : backend reads via predict_for_country()
"""

from __future__ import annotations

import csv
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import joblib

# Reject predictions older than this. run_predict.py is designed to be re-run
# at least once a day, so anything older than the GDELT update cadence is stale.
_MAX_PREDICTION_AGE_DAYS = 3

_ML_DIR     = Path(__file__).parents[2] / "data"
_MODEL_DIR  = _ML_DIR / "models"
_MAPPING_CSV = Path(__file__).parents[3] / "config" / "country_asset_mapping.csv"

# ISO-2 → GDELT country code lookup (built once from the mapping CSV)
_ISO2_TO_GDELT: dict[str, str] = {}
_GDELT_TO_ISO2: dict[str, str] = {}

_META: Optional[dict] = None


def _load_mapping() -> None:
    global _ISO2_TO_GDELT, _GDELT_TO_ISO2
    if not _MAPPING_CSV.exists():
        return
    with _MAPPING_CSV.open("r", encoding="utf-8", newline="") as handle:
        for row in csv.DictReader(handle):
            gdelt = row.get("gdelt_country_code", "").strip()
            iso2  = row.get("iso2", "").strip().upper()
            if gdelt and iso2:
                _ISO2_TO_GDELT[iso2] = gdelt
                _GDELT_TO_ISO2[gdelt] = iso2


def _load_meta() -> None:
    """Load ensemble metadata from direction or volatility model dir."""
    global _META
    if _META is not None:
        return
    for subdir in ("direction", "volatility"):
        meta_path = _MODEL_DIR / subdir / "ensemble_meta.joblib"
        if meta_path.exists():
            try:
                _META = joblib.load(meta_path)
                return
            except Exception as exc:
                print(f"[predictor] failed to load meta from {subdir}: {exc}")
    _META = {}


def _parse_iso(raw: str) -> Optional[datetime]:
    if not raw:
        return None
    try:
        dt = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


def _is_fresh(doc: dict) -> bool:
    dt = _parse_iso(doc.get("computed_at", ""))
    if dt is None:
        return False
    age_days = (datetime.now(timezone.utc) - dt).total_seconds() / 86400.0
    return age_days <= _MAX_PREDICTION_AGE_DAYS


def _read_prediction(iso2: str) -> Optional[dict]:
    """Return the stored prediction doc from MongoDB, or None if absent."""
    try:
        from pymongo import MongoClient
        from config.settings import settings
        client = MongoClient(settings.MONGODB_URI, serverSelectionTimeoutMS=2000)
        doc = client[settings.MONGODB_DB]["ml_predictions"].find_one(
            {"iso2": iso2.upper()}, {"_id": 0}
        )
        client.close()
        return doc or None
    except Exception:
        return None


def predict_for_country(iso2: str) -> dict:
    """
    Returns:
      direction      : "increase" | "decrease" | "uncertain" | None
      probability    : float 0–1 | None
      confidence_pct : "73%" style | None
      used_ml        : bool — True only when a fresh ml_predictions row exists
      data_source    : "mongodb" | "none"
      feature_date   : GDELT date the features came from, or ""
      no_data_reason : plain-English reason when used_ml is False
    """
    _load_meta()

    # Normalise ISO so we don't miss a row due to casing
    iso2_up = iso2.upper()

    # Country must be in the asset mapping at all — predictions only exist for mapped ISOs.
    if not _ISO2_TO_GDELT:
        _load_mapping()
    if iso2_up not in _ISO2_TO_GDELT:
        return {
            "direction": None, "probability": None, "confidence_pct": None,
            "used_ml": False, "data_source": "none", "feature_date": "",
            "no_data_reason": "Country not in market coverage mapping (no ETF assigned).",
        }

    doc = _read_prediction(iso2_up)
    if doc is None:
        return {
            "direction": None, "probability": None, "confidence_pct": None,
            "used_ml": False, "data_source": "none", "feature_date": "",
            "no_data_reason": (
                "No prediction stored for this country yet. "
                "Run: python ml/scripts/models/run_predict.py"
            ),
        }

    if not _is_fresh(doc):
        return {
            "direction": None, "probability": None, "confidence_pct": None,
            "used_ml": False, "data_source": "none",
            "feature_date":   doc.get("feature_date", ""),
            "no_data_reason": (
                f"Stored prediction is older than {_MAX_PREDICTION_AGE_DAYS} days "
                f"(computed_at={doc.get('computed_at','')[:19]}). "
                "Re-run: python ml/scripts/models/run_predict.py"
            ),
        }

    return {
        # Direction model (label_up_3d)
        "direction":      doc.get("direction") or doc.get("vix_direction"),
        "direction_prob": doc.get("direction_prob") or doc.get("probability"),
        "direction_pct":  doc.get("direction_pct") or doc.get("confidence_pct"),
        "direction_auc":  doc.get("direction_auc"),
        # Volatility model (label_vol_high_5d)
        "vol_level":      doc.get("vol_level"),
        "vol_prob":       doc.get("vol_prob"),
        "vol_pct":        doc.get("vol_pct"),
        "vol_auc":        doc.get("vol_auc"),
        # Combined
        "risk_level":     doc.get("risk_level", "MEDIUM"),
        # Legacy
        "probability":    doc.get("probability"),
        "confidence_pct": doc.get("confidence_pct"),
        "used_ml":        True,
        "data_source":    "mongodb",
        "feature_date":   doc.get("feature_date", ""),
        "no_data_reason": "",
    }


def get_meta() -> dict:
    if _META is None:
        _load_meta()
    if not _META:
        return {}
    return {
        "target":   _META.get("target", ""),
        "test_auc": _META.get("test_auc", ""),
        "models":   ["lgbm", "xgb", "catboost"],
    }
