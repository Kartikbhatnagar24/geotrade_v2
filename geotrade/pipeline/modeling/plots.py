"""
pipeline/modeling/plots.py
───────────────────────────
Generates and saves all result charts to data/plots/.
Dark-theme, thesis-ready figures.
"""

import os
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")  # headless — safe on Windows without a display
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
from sklearn.metrics import RocCurveDisplay

from config.settings import settings

# ── Colour palette ────────────────────────────────────────────
C = {
    "bg":        "#050b14",
    "panel":     "#0d1627",
    "blue":      "#38bdf8",
    "red":       "#ef4444",
    "amber":     "#f59e0b",
    "green":     "#22c55e",
    "purple":    "#a855f7",
    "white":     "#f1f5f9",
    "muted":     "#64748b",
}

plt.rcParams.update({
    "figure.facecolor":  C["bg"],
    "axes.facecolor":    C["panel"],
    "axes.edgecolor":    C["muted"],
    "axes.labelcolor":   C["white"],
    "xtick.color":       C["muted"],
    "ytick.color":       C["muted"],
    "text.color":        C["white"],
    "grid.color":        "#1e2d45",
    "grid.linestyle":    "--",
    "grid.alpha":        0.5,
    "legend.facecolor":  C["panel"],
    "legend.edgecolor":  C["muted"],
    "font.family":       "monospace",
})

_PLOT_DIR = settings.DATA_PLOTS


def _save(fig, name: str) -> str:
    _PLOT_DIR.mkdir(parents=True, exist_ok=True)
    path = _PLOT_DIR / name
    fig.savefig(path, dpi=150, bbox_inches="tight", facecolor=C["bg"])
    plt.close(fig)
    return str(path)


# ── Plot 1: Tension vs Volatility timeline ────────────────────

def plot_tension_vs_volatility(merged: pd.DataFrame) -> str:
    fig, axes = plt.subplots(3, 1, figsize=(14, 11), sharex=True)
    fig.suptitle("Global Tension vs Market Volatility", fontsize=15,
                 fontweight="bold", y=1.01, color=C["white"])

    dates = pd.to_datetime(merged["date"])

    # VIX
    ax = axes[0]
    ax.fill_between(dates, merged["vix_close"], alpha=0.25, color=C["red"])
    ax.plot(dates, merged["vix_close"], color=C["red"], lw=1.5, label="VIX")
    ax.set_ylabel("VIX")
    ax.legend(loc="upper right")
    ax.grid(True)

    # Global tension
    ax = axes[1]
    ax.fill_between(dates, merged["global_tension"], alpha=0.25, color=C["blue"])
    ax.plot(dates, merged["global_tension"], color=C["blue"], lw=1.5, label="Global Tension")
    ax.axhline(0.65, color=C["red"],   lw=0.8, ls=":", alpha=0.6, label="High threshold")
    ax.axhline(0.35, color=C["amber"], lw=0.8, ls=":", alpha=0.6, label="Med threshold")
    ax.set_ylabel("Tension Score")
    ax.legend(loc="upper right", fontsize=8)
    ax.grid(True)

    # Volatility label
    ax = axes[2]
    colors = [C["red"] if v == 1 else C["green"] for v in merged["volatility_increase"]]
    ax.scatter(dates, merged["volatility_increase"], c=colors, s=18, alpha=0.55)
    ax.set_ylabel("Vol. Increase\n(1 = Yes)")
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%b %Y"))
    fig.autofmt_xdate(rotation=20)
    ax.grid(True)

    plt.tight_layout()
    return _save(fig, "tension_vs_volatility.png")


# ── Plot 2: Feature importance bar chart ─────────────────────

def plot_feature_importance(result: dict) -> str:
    features    = result["features"]
    importances = result["importances"]
    name        = result["name"]

    idx = np.argsort(importances)
    fig, ax = plt.subplots(figsize=(10, 7))
    ax.set_title(f"Feature Importance — {name}", fontsize=13, fontweight="bold")

    bar_colors = [C["blue"] if i == idx[-1] else C["purple"] for i in range(len(idx))]
    bars = ax.barh(
        [features[i] for i in idx],
        importances[idx],
        color=bar_colors,
        edgecolor="none",
        alpha=0.85,
    )
    for bar, val in zip(bars, importances[idx]):
        ax.text(val + 0.002, bar.get_y() + bar.get_height() / 2,
                f"{val:.3f}", va="center", fontsize=9, color=C["muted"])

    ax.set_xlabel("Importance")
    ax.grid(True, axis="x")
    plt.tight_layout()
    return _save(fig, f"feature_importance_{name.lower()}.png")


# ── Plot 3: ROC curves ────────────────────────────────────────

def plot_roc_curves(results: list[dict], y_test) -> str:
    palette = [C["blue"], C["amber"], C["green"], C["purple"]]
    fig, ax = plt.subplots(figsize=(8, 7))
    ax.set_title("ROC Curves — Volatility Prediction", fontsize=13, fontweight="bold")

    for result, color in zip(results, palette):
        RocCurveDisplay.from_predictions(
            y_test, result["y_prob"],
            name=f"{result['name']} (AUC={result['roc_auc']:.3f})",
            ax=ax, color=color,
        )

    ax.plot([0, 1], [0, 1], ls="--", color=C["muted"], alpha=0.5, label="Random (0.5)")
    ax.set_xlabel("False Positive Rate")
    ax.set_ylabel("True Positive Rate")
    ax.legend(fontsize=9)
    ax.grid(True)
    plt.tight_layout()
    return _save(fig, "roc_curves.png")


# ── Plot 4: Model comparison bar chart ───────────────────────

def plot_model_comparison(results: list[dict]) -> str:
    metrics = ["accuracy", "f1", "roc_auc"]
    labels  = [r["name"] for r in results]
    x       = np.arange(len(metrics))
    width   = 0.35
    palette = [C["blue"], C["amber"]]

    fig, ax = plt.subplots(figsize=(9, 6))
    ax.set_title("Model Comparison", fontsize=13, fontweight="bold")

    for i, (result, color) in enumerate(zip(results, palette)):
        vals = [result[m] for m in metrics]
        bars = ax.bar(x + i * width, vals, width, label=result["name"],
                      color=color, alpha=0.85, edgecolor="none")
        for bar, v in zip(bars, vals):
            ax.text(bar.get_x() + bar.get_width() / 2, v + 0.01,
                    f"{v:.3f}", ha="center", va="bottom", fontsize=9)

    ax.set_xticks(x + width / 2)
    ax.set_xticklabels(["Accuracy", "F1 Score", "ROC-AUC"])
    ax.set_ylim(0, 1.1)
    ax.set_ylabel("Score")
    ax.legend()
    ax.grid(True, axis="y")
    plt.tight_layout()
    return _save(fig, "model_comparison.png")
