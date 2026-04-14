"""
pipeline/nlp/models.py
───────────────────────
Loads HuggingFace pipelines once and caches them.
First run downloads ~1 GB of model weights.

torch is imported lazily so this module can be safely imported
even when torch is not installed (e.g. during step4_model.py which
only needs the keyword classifier, not the transformers pipeline).
"""

from transformers import pipeline as hf_pipeline

_classifier = None
_sentiment  = None


def _device() -> int:
    """Resolve GPU/CPU device lazily — only called when a pipeline starts."""
    try:
        import torch
        return 0 if torch.cuda.is_available() else -1
    except ImportError:
        return -1


def get_classifier():
    """Zero-shot event classifier (facebook/bart-large-mnli)."""
    global _classifier
    if _classifier is None:
        print("  [NLP] Loading zero-shot classifier...")
        _classifier = hf_pipeline(
            "zero-shot-classification",
            model="facebook/bart-large-mnli",
            device=_device(),
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
            device=_device(),
        )
    return _sentiment
