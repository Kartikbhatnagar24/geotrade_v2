"""
pipeline/nlp/classifier.py
───────────────────────────
Keyword-based news type classifier.
Returns one of: conflict | sanctions | military | economic | diplomatic |
                humanitarian | other

No extra ML model required — fast, offline-capable.
"""

import re
from typing import Literal

NewsType = Literal[
    "conflict", "sanctions", "military", "economic",
    "diplomatic", "humanitarian", "other"
]

# ── Keyword → category map (priority order) ───────────────────
_PATTERNS: list[tuple[NewsType, list[str]]] = [
    ("military", [
        "missile", "airstrike", "air strike", "bomb", "nuclear", "weapon",
        "drone", "warship", "fighter jet", "aircraft carrier", "troops",
        "soldier", "military", "navy", "army", "ballistic", "icbm",
        "artillery", "ammunition", "pentagon", "nato troops",
    ]),
    ("conflict", [
        "war", "battle", "attack", "invasion", "conflict", "ceasefire",
        "cease-fire", "shelling", "hostage", "insurgent", "rebel",
        "civil war", "frontline", "offensive", "counteroffensive",
        "occupation", "territory", "clashes", "casualties",
    ]),
    ("sanctions", [
        "sanction", "embargo", "ban", "restriction", "blacklist",
        "freeze asset", "export control", "technology ban", "financial ban",
        "swift", "trade restriction",
    ]),
    ("economic", [
        "tariff", "trade war", "gdp", "recession", "inflation", "currency",
        "interest rate", "imf", "world bank", "debt", "export", "import",
        "supply chain", "oil price", "commodity", "rare earth", "semiconductor",
    ]),
    ("diplomatic", [
        "diplomat", "ambassador", "summit", "treaty", "negotiation",
        "talks", "agreement", "accord", "envoy", "foreign minister",
        "secretary of state", "united nations", "un security council",
        "g7", "g20", "bilateral",
    ]),
    ("humanitarian", [
        "refugee", "displaced", "famine", "humanitarian", "aid",
        "civilian", "evacuation", "casualt", "death toll", "humanitarian crisis",
        "world food programme", "unhcr",
    ]),
]


def classify_news_type(text: str) -> NewsType:
    """Classify a news headline/description into a geopolitical category."""
    lowered = text.lower()
    for category, keywords in _PATTERNS:
        for kw in keywords:
            if re.search(r"\b" + re.escape(kw) + r"\b", lowered):
                return category
    return "other"


def classify_articles(articles: list[dict]) -> list[dict]:
    """
    Classify a list of article dicts in-place.
    Adds 'news_type' field to each article.
    """
    for art in articles:
        combined = f"{art.get('title', '')} {art.get('description', '')}"
        art["news_type"] = classify_news_type(combined)
    return articles
