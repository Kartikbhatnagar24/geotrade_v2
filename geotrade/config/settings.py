"""
config/settings.py
──────────────────
Single place where ALL environment variables are read and validated.
Every other module imports from here — never from os.getenv directly.

Usage:
    from config.settings import settings
    print(settings.MONGODB_URI)
"""

import os
from pathlib import Path
from dotenv import load_dotenv

# Load .env from project root (works regardless of CWD)
_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(_ROOT / ".env")


class Settings:
    # ── MongoDB ───────────────────────────────────────────────
    MONGODB_URI: str  = os.getenv("MONGODB_URI", "mongodb://localhost:27017")
    MONGODB_DB:  str  = os.getenv("MONGODB_DB",  "geotrade")

    # ── Collections ───────────────────────────────────────────
    COL_RAW_ARTICLES:    str = "raw_articles"
    COL_PROCESSED_EVENTS: str = "processed_events"
    COL_DAILY_SIGNALS:   str = "daily_signals"

    # ── News ingestion ────────────────────────────────────────
    NEWS_API_KEY:       str = os.getenv("NEWS_API_KEY", "")
    GUARDIAN_API_KEY:   str = os.getenv("GUARDIAN_API_KEY", "")
    INGESTION_DAYS_BACK: int = int(os.getenv("INGESTION_DAYS_BACK", "30"))
    MAX_ARTICLES:       int = int(os.getenv("MAX_ARTICLES_PER_RUN", "500"))

    # ── NLP ───────────────────────────────────────────────────
    NLP_BATCH_SIZE:     int = int(os.getenv("NLP_BATCH_SIZE", "8"))
    EVENT_LABELS:       list = ["conflict", "military", "diplomacy", "sanctions", "elections", "trade"]

    # ── Tension scoring ───────────────────────────────────────
    # α · neg_sentiment + β · conflict_gravity + γ · coverage_signal
    # Weights grounded in Caldara-Iacoviello (2022) and CAMEO/Goldstein literature.
    TENSION_ALPHA:      float = float(os.getenv("TENSION_ALPHA", "0.50"))
    TENSION_BETA:       float = float(os.getenv("TENSION_BETA",  "0.35"))
    TENSION_GAMMA:      float = float(os.getenv("TENSION_GAMMA", "0.15"))

    # ── Paths ─────────────────────────────────────────────────
    ROOT_DIR:       Path = _ROOT
    DATA_RAW:       Path = _ROOT / "data" / "raw"
    DATA_PROCESSED: Path = _ROOT / "data" / "processed"
    DATA_PLOTS:     Path = _ROOT / "data" / "plots"

    # ── Gemini AI ─────────────────────────────────────────────
    GEMINI_API_KEY: str = os.getenv("GEMINI_API_KEY", "")

    # ── Forecast / Briefing collections ───────────────────────
    COL_TENSION_FORECASTS: str = "tension_forecasts"
    COL_LLM_BRIEFINGS:     str = "llm_briefings"
    COL_ML_PREDICTIONS:    str = "ml_predictions"

    # ── Forecast settings ─────────────────────────────────────
    FORECAST_HORIZON_DAYS:  int   = 7     # how many days ahead to predict
    FORECAST_HISTORY_DAYS:  int   = 30    # how many days of history to use
    FORECAST_CACHE_MINUTES: int   = 60    # re-compute after N minutes
    BRIEFING_CACHE_HOURS:   int   = 24    # re-call Gemini after N hours

    # ── API ───────────────────────────────────────────────────
    API_HOST:       str = os.getenv("API_HOST", "0.0.0.0")
    API_PORT:       int = int(os.getenv("API_PORT", "8000"))


settings = Settings()


def print_config():
    """Pretty-print current config (masks secrets)."""
    uri = settings.MONGODB_URI
    masked_uri = uri if "localhost" in uri else uri[:20] + "***"
    print(f"""
  GeoTrade Config
  ───────────────────────────────────
  MongoDB URI   : {masked_uri}
  Database      : {settings.MONGODB_DB}
  NewsAPI key   : {"set ✓" if settings.NEWS_API_KEY else "not set (RSS fallback)"}
  Gemini key    : {"set ✓" if settings.GEMINI_API_KEY else "not set (briefings disabled)"}
  Days back     : {settings.INGESTION_DAYS_BACK}
  Max articles  : {settings.MAX_ARTICLES}
  NLP batch     : {settings.NLP_BATCH_SIZE}
  Tension α/β/γ : {settings.TENSION_ALPHA} / {settings.TENSION_BETA} / {settings.TENSION_GAMMA}
  Forecast      : {settings.FORECAST_HORIZON_DAYS}d ahead, {settings.FORECAST_HISTORY_DAYS}d history
  API           : {settings.API_HOST}:{settings.API_PORT}
  ───────────────────────────────────""")


if __name__ == "__main__":
    print_config()
