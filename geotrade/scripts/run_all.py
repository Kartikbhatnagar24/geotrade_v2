"""
scripts/run_all.py — Full Pipeline Runner
==========================================
Runs all 4 steps in sequence. Stops on first failure.

Usage:
    python scripts/run_all.py              # all steps
    python scripts/run_all.py --from 3     # resume from step 3
    python scripts/run_all.py --only 1 2   # run specific steps
"""

import argparse
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

STEPS = {
    1: "scripts/step1_ingest.py",
    2: "scripts/step2_nlp.py",
    3: "scripts/step3_score.py",
    4: "scripts/step4_model.py",
}

NAMES = {
    1: "News Ingestion",
    2: "NLP Processing",
    3: "Tension Scoring",
    4: "Market Modeling",
}


def run(step: int) -> bool:
    script = ROOT / STEPS[step]
    print(f"\n{'━' * 56}")
    print(f"  [{step}/4] {NAMES[step]}")
    print(f"{'━' * 56}")
    t = time.time()
    ok = subprocess.run([sys.executable, str(script)], cwd=str(ROOT)).returncode == 0
    elapsed = time.time() - t
    if ok:
        print(f"  ✓ Done in {elapsed:.1f}s")
    else:
        print(f"  ✗ FAILED after {elapsed:.1f}s")
    return ok


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--from", dest="from_step", type=int, default=1)
    parser.add_argument("--only", nargs="+", type=int)
    args = parser.parse_args()

    to_run = sorted(args.only) if args.only else list(range(args.from_step, 5))

    print(f"\n{'═' * 56}")
    print(f"  GeoTrade — Full Pipeline")
    print(f"  Steps: {to_run}")
    print(f"{'═' * 56}")

    results: dict[int, bool] = {}
    total_start = time.time()

    for step in to_run:
        ok = run(step)
        results[step] = ok
        if not ok:
            print(f"\n  Pipeline stopped at step {step}.")
            print(f"  Resume with: python scripts/run_all.py --from {step}")
            break

    total = time.time() - total_start
    print(f"\n{'═' * 56}")
    print(f"  RESULTS  ({total:.0f}s total)")
    print(f"{'─' * 56}")
    for s, ok in results.items():
        mark = "✓" if ok else "✗"
        print(f"  {mark} Step {s}: {NAMES[s]}")
    print(f"{'═' * 56}")

    if all(results.values()):
        print("\n  All steps done. Start the system:\n")
        print("    Backend  : cd backend && uvicorn main:app --reload")
        print("    Frontend : cd frontend && npm run dev")
        print("    Open     : http://localhost:3000\n")


if __name__ == "__main__":
    main()
