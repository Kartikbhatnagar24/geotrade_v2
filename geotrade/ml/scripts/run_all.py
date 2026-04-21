"""
scripts/run_all.py — Full Pipeline Runner
==========================================
Runs all 5 steps in sequence. Stops on first failure.

Usage (from geotrade/ root):
    python ml/scripts/run_all.py              # all 5 steps
    python ml/scripts/run_all.py --from 3     # resume from step 3
    python ml/scripts/run_all.py --only 1 2   # run only specific steps
    python ml/scripts/run_all.py --skip 4     # skip step 4 (modeling)

Step overview:
    1  News Ingestion     — fetch articles from GDELT, RSS, NewsAPI, Guardian
    2  NLP Processing     — classify events, sentiment, country extraction
    3  Tension Scoring    — compute daily tension scores per country
    4  Market Modeling    — train RandomForest + LightGBM, save best model
    5  Forecast Cache     — pre-compute 7-day tension forecasts for all countries

Notes:
    - Step 2 downloads ~1 GB of HuggingFace models on first run (BART + DistilBERT)
    - Step 4 requires yfinance access (internet). Skips gracefully with synthetic data if offline.
    - Step 5 is fast (<10s) and safe to re-run anytime.
    - You can safely skip step 4 with --skip 4 if you only want the globe + forecast.
"""

import argparse
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent  # geotrade root

STEPS = {
    1: "ml/scripts/step1_ingest.py",
    2: "ml/scripts/step2_nlp.py",
    3: "ml/scripts/step3_score.py",
    4: "ml/scripts/step4_model.py",
    5: "ml/scripts/step5_forecast.py",
}

NAMES = {
    1: "News Ingestion",
    2: "NLP Processing",
    3: "Tension Scoring",
    4: "Market Modeling",
    5: "Forecast Cache",
}

NOTES = {
    1: "Fetches from GDELT + 16 RSS feeds + NewsAPI/Guardian if keys set",
    2: "Runs BART zero-shot + DistilBERT sentiment + country NER (slow on first run)",
    3: "Computes intensity-weighted tension scores, writes daily_signals",
    4: "Trains RF + LightGBM on tension+VIX, saves best model to data/models/",
    5: "Pre-computes 7-day forecasts for all countries, writes tension_forecasts",
}


def run(step: int) -> bool:
    script = ROOT / STEPS[step]
    print(f"\n{'━' * 60}")
    print(f"  Step {step}/5 — {NAMES[step]}")
    print(f"  {NOTES[step]}")
    print(f"{'━' * 60}")
    t  = time.time()
    ok = subprocess.run(
        [sys.executable, str(script)], cwd=str(ROOT)
    ).returncode == 0
    elapsed = time.time() - t
    status  = "✓ Done" if ok else "✗ FAILED"
    print(f"\n  {status} in {elapsed:.1f}s")
    return ok


def main():
    parser = argparse.ArgumentParser(description="GeoTrade pipeline runner")
    parser.add_argument("--from",  dest="from_step", type=int, default=1,
                        help="Start from this step (default: 1)")
    parser.add_argument("--only",  nargs="+", type=int,
                        help="Run only these steps, e.g. --only 1 3")
    parser.add_argument("--skip",  nargs="+", type=int, default=[],
                        help="Skip these steps, e.g. --skip 4")
    args = parser.parse_args()

    if args.only:
        to_run = sorted(args.only)
    else:
        to_run = [s for s in range(args.from_step, 6) if s not in args.skip]

    print(f"\n{'═' * 60}")
    print(f"  GeoTrade — Pipeline Runner")
    print(f"  Running steps: {to_run}")
    if args.skip:
        print(f"  Skipping:      {args.skip}")
    print(f"{'═' * 60}")

    results: dict[int, bool] = {}
    total_start = time.time()

    for step in to_run:
        ok = run(step)
        results[step] = ok
        if not ok:
            print(f"\n  Pipeline stopped at step {step}.")
            print(f"  Fix the error above, then resume with:")
            print(f"    python ml/scripts/run_all.py --from {step}")
            break

    total = time.time() - total_start

    print(f"\n{'═' * 60}")
    print(f"  RESULTS  ({total:.0f}s total)")
    print(f"{'─' * 60}")
    for s, ok in results.items():
        mark = "✓" if ok else "✗"
        print(f"  {mark}  Step {s}: {NAMES[s]}")
    print(f"{'═' * 60}")

    if all(results.values()):
        print("\n  All steps complete. Start the system:\n")
        print("    Backend  :  uvicorn backend.main:app --reload --port 8000")
        print("    Frontend :  cd frontend && npm run dev")
        print("    Open     :  http://localhost:3000")
        print("    API docs :  http://localhost:8000/docs\n")
    else:
        failed = [s for s, ok in results.items() if not ok]
        print(f"\n  Failed steps: {failed}")
        print(f"  Tip: Step 4 (modeling) can be skipped safely:")
        print(f"    python ml/scripts/run_all.py --skip 4\n")


if __name__ == "__main__":
    main()
