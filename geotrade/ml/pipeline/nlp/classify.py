"""
pipeline/nlp/classify.py
─────────────────────────
Event classification and sentiment analysis functions.
"""

from config.settings import settings
from pipeline.utils.text import truncate
from pipeline.nlp.models import get_classifier, get_sentiment


def classify_event(text: str) -> tuple[str, float]:
    """
    Zero-shot classify text into one of settings.EVENT_LABELS.
    Returns (label, confidence_score).
    """
    if not text.strip():
        return "unknown", 0.0
    try:
        result = get_classifier()(
            truncate(text, 512),
            candidate_labels=settings.EVENT_LABELS,
            multi_label=False,
        )
        return result["labels"][0], float(result["scores"][0])
    except Exception as e:
        print(f"    [classify] {e}")
        return "unknown", 0.0


def analyze_sentiment(text: str) -> tuple[str, float]:
    """
    Analyze sentiment. Returns (label, score).
    label: 'POSITIVE' | 'NEGATIVE'
    score: model confidence in [0, 1]
    """
    if not text.strip():
        return "NEUTRAL", 0.5
    try:
        result = get_sentiment()(truncate(text, 512))[0]
        return result["label"], float(result["score"])
    except Exception as e:
        print(f"    [sentiment] {e}")
        return "NEUTRAL", 0.5


def neg_score(label: str, score: float) -> float:
    """
    Convert sentiment output to a negativity score in [0, 1].
    NEGATIVE confidence maps directly; POSITIVE is inverted.
    """
    return score if label == "NEGATIVE" else 1.0 - score
