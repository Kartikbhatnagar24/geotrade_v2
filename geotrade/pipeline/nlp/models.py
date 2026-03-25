"""
pipeline/nlp/models.py
───────────────────────
Loads HuggingFace pipelines once and caches them.
First run downloads ~1 GB of model weights.
"""

import torch
from transformers import pipeline as hf_pipeline

_classifier    = None
_sentiment     = None

_DEVICE = 0 if torch.cuda.is_available() else -1


def get_classifier():
    """Zero-shot event classifier (facebook/bart-large-mnli)."""
    global _classifier
    if _classifier is None:
        print("  [NLP] Loading zero-shot classifier...")
        _classifier = hf_pipeline(
            "zero-shot-classification",
            model="facebook/bart-large-mnli",
            device=_DEVICE,
        )
    return _classifier


def get_sentiment():
    """Sentiment analyzer (distilbert SST-2)."""
    global _sentiment
    if _sentiment is None:
        print("  [NLP] Loading sentiment analyzer...")
        _sentiment = hf_pipeline(
            "sentiment-analysis",
            model="distilbert-base-uncased-finetuned-sst-2-english",
            device=_DEVICE,
        )
    return _sentiment
