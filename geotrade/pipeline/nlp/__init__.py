"""
pipeline/nlp/__init__.py
─────────────────────────
Public API for the NLP pipeline.

classify_event / analyze_sentiment / neg_score are loaded lazily
so that importing this package (e.g. by features.py calling
classify_news_type from classifier.py) does NOT require torch or
transformers to be installed.
"""

from pipeline.nlp.ner import extract_countries
from pipeline.nlp.store import fetch_unprocessed, save_event, label_distribution


def classify_event(text: str):
    from pipeline.nlp.classify import classify_event as _fn
    return _fn(text)


def analyze_sentiment(text: str):
    from pipeline.nlp.classify import analyze_sentiment as _fn
    return _fn(text)


def neg_score(label: str, score: float) -> float:
    from pipeline.nlp.classify import neg_score as _fn
    return _fn(label, score)


__all__ = [
    "classify_event", "analyze_sentiment", "neg_score",
    "extract_countries",
    "fetch_unprocessed", "save_event", "label_distribution",
]
