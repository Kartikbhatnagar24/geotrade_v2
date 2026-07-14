"""
scripts/run_all.py — Full Pipeline Runner
==========================================
Runs the 3 active pipeline steps in sequence. Stops on first failure.

Usage (from geotrade/ root):
    python ml/scripts/run_all.py              # all 3 steps
    python ml/scripts/run_all.py --from 2     # resume from step 2
    python ml/scripts/run_all.py --only 1 3   # run only specific steps

Step overview:
    1  News Ingestion     — fetch articles from GDELT, RSS, NewsAPI, Guardian
    2  NLP Processing     — classify events, sentiment, country extraction
    3  Tension Scoring    — compute daily tension scores per country

Active model pipeline (separate, run after steps 1-3):
    Train  : python ml/scripts/models/train_boosted_ensemble.py
    Predict: python ml/scripts/models/run_predict.py   (writes ml_predictions to MongoDB)

Notes:
    - Step 2 downloads ~1 GB of HuggingFace models on first run (BART + DistilBERT)
    - The old RF+LightGBM approach (step4_model.py) has been moved to
      ml/scripts/outdated/ — the active model is the LightGBM/XGB/CatBoost ensemble.
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
    4: "ml/scripts/maintain_db.py",
}

NAMES = {
    1: "News Ingestion",
    2: "NLP Processing",
    3: "Tension Scoring",
    4: "DB Maintenance",
}

NOTES = {
    1: "Fetches from GDELT + 16 RSS feeds + NewsAPI/Guardian if keys set",
    2: "Runs BART zero-shot + DistilBERT sentiment + country NER (slow on first run)",
    3: "Computes intensity-weighted tension scores, writes daily_signals",
    4: "Sweeps phantom rows + enforces retention across all collections",
}

LAST_STEP = max(STEPS)


def run(step: int) -> bool:
    script = ROOT / STEPS[step]
    print(f"\n{'â”' * 60}")
    print(f"  Step {step}/{LAST_STEP} — {NAMES[step]}")
    print(f"  {NOTES[step]}")
    print(f"{'â”' * 60}")
    t  = time.time()
    ok = subprocess.run(
        [sys.executable, str(script)], cwd=str(ROOT)
    ).returncode == 0
    elapsed = time.time() - t
    status  = "âœ“ Done" if ok else "âœ— FAILED"
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
        to_run = [s for s in range(args.from_step, LAST_STEP + 1) if s not in args.skip]

    print(f"\n{'â•' * 60}")
    print(f"  GeoTrade â€” Pipeline Runner")
    print(f"  Running steps: {to_run}")
    if args.skip:
        print(f"  Skipping:      {args.skip}")
    print(f"{'â•' * 60}")

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

    print(f"\n{'â•' * 60}")
    print(f"  RESULTS  ({total:.0f}s total)")
    print(f"{'â”€' * 60}")
    for s, ok in results.items():
        mark = "âœ“" if ok else "âœ—"
        print(f"  {mark}  Step {s}: {NAMES[s]}")
    print(f"{'â•' * 60}")

    if all(results.values()):
        print("\n  All steps complete.\n")
        print("  Next: run the model pipeline to refresh trading predictions:")
        print("    python ml/scripts/models/run_predict.py")
        print("\n  Then start the system:")
        print("    Backend  :  uvicorn backend.main:app --reload --port 8000")
        print("    Frontend :  cd frontend && npm run dev")
        print("    Open     :  http://localhost:3000")
        print("    API docs :  http://localhost:8000/docs\n")
    else:
        failed = [s for s, ok in results.items() if not ok]
        print(f"\n  Failed steps: {failed}")


if __name__ == "__main__":
    main()

