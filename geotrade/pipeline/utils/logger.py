"""
pipeline/utils/logger.py
─────────────────────────
Simple step-aware logger so every pipeline script prints consistently.
"""

import sys
from datetime import datetime


class StepLogger:
    def __init__(self, step_name: str):
        self.step_name = step_name
        self._start = datetime.now()

    def header(self):
        print(f"\n{'═' * 58}")
        print(f"  GeoTrade Pipeline — {self.step_name}")
        print(f"  Started : {self._start.strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"{'═' * 58}")

    def info(self, msg: str):
        print(f"  ▸ {msg}")

    def success(self, msg: str):
        print(f"  ✓ {msg}")

    def warn(self, msg: str):
        print(f"  ⚠ {msg}", file=sys.stderr)

    def error(self, msg: str):
        print(f"  ✗ {msg}", file=sys.stderr)

    def section(self, title: str):
        print(f"\n  [{title}]")

    def footer(self, summary: dict | None = None):
        elapsed = (datetime.now() - self._start).seconds
        print(f"\n{'─' * 58}")
        if summary:
            for k, v in summary.items():
                print(f"  {k:<28} {v}")
        print(f"  {'Elapsed':<28} {elapsed}s")
        print(f"{'═' * 58}\n")
