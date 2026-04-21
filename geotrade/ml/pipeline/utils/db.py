"""
pipeline/utils/db.py
─────────────────────
MongoDB connection singleton.
All pipeline modules import get_db() from here.

Usage:
    from pipeline.utils.db import get_db
    col = get_db()["raw_articles"]
"""

from pymongo import MongoClient
from pymongo.database import Database
from config.settings import settings

_client: MongoClient | None = None


def get_client() -> MongoClient:
    """Return a cached MongoClient. Connects on first call."""
    global _client
    if _client is None:
        _client = MongoClient(
            settings.MONGODB_URI,
            serverSelectionTimeoutMS=6000,
            connectTimeoutMS=6000,
        )
        _client.admin.command("ping")   # fail fast if unreachable
        print(f"[MongoDB] Connected → {settings.MONGODB_DB}")
    return _client


def get_db() -> Database:
    """Return the geotrade Database handle."""
    return get_client()[settings.MONGODB_DB]


def close_connection():
    """Explicitly close the connection (useful in scripts)."""
    global _client
    if _client:
        _client.close()
        _client = None
        print("[MongoDB] Connection closed")
