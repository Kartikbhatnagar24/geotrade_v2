"""
backend/core/database.py
─────────────────────────
MongoDB connection for the FastAPI server.
Reads MONGODB_URI from .env — works with Atlas cloud URIs.
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from pymongo import MongoClient
from pymongo.database import Database
from config.settings import settings

_client: MongoClient | None = None


def get_client() -> MongoClient:
    global _client
    if _client is None:
        _client = MongoClient(
            settings.MONGODB_URI,
            serverSelectionTimeoutMS=8000,
            tls=True if "mongodb+srv" in settings.MONGODB_URI else False,
        )
    return _client


def get_db() -> Database:
    return get_client()[settings.MONGODB_DB]


def ping() -> bool:
    try:
        get_client().admin.command("ping")
        return True
    except Exception:
        return False
