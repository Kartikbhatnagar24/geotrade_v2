#!/usr/bin/env python3
"""
Compute cross-country breadth features from daily GDELT aggregates.

For each calendar date, counts how many countries simultaneously show:
  - above-median news volume (relative to their own trailing 30-day median)
  - negative average tone

These become global stress indicators: when 20/25 countries spike together,
something systemic is happening that will lift volatility everywhere.
Output is keyed by date (YYYYMMDD) to match the rolling features format.
"""

from __future__ import annotations

import argparse
import csv
import datetime as dt
from collections import defaultdict, deque
from pathlib import Path

LOOKBACK = 30
MIN_OBS = 5


def parse_date(value: str) -> dt.date:
    return dt.datetime.strptime(value, "%Y%m%d").date()


def format_date(value: dt.date) -> str:
    return value.strftime("%Y%m%d")


def daterange(start: dt.date, end: dt.date):
    current = start
    while current <= end:
        yield current
        current += dt.timedelta(days=1)


def rolling_median(dq: deque) -> float:
    s = sorted(dq)
    return s[len(s) // 2]


def main() -> int:
    parser = argparse.ArgumentParser(description="Build cross-country GDELT breadth features.")
    parser.add_argument("--input-file", default="ml/data/processed/gdelt_country_daily_2y.csv")
    parser.add_argument("--output-file", default="ml/data/working/gdelt_breadth_daily.csv")
    args = parser.parse_args()

    input_path = Path(args.input_file)
    output_path = Path(args.output_file)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    # Load: daily[country][date] = {document_count, avg_tone_mean}
    daily: dict[str, dict[str, dict]] = defaultdict(dict)
    all_dates: set[str] = set()
    with input_path.open("r", encoding="utf-8", newline="") as handle:
        for row in csv.DictReader(handle):
            country = row["country_code"]
            date = row["date"]
            all_dates.add(date)
            try:
                daily[country][date] = {
                    "doc_count": float(row.get("document_count") or 0),
                    "tone": float(row.get("avg_tone_mean") or 0),
                }
            except ValueError:
                pass

    all_countries = sorted(daily.keys())
    start_date = parse_date(min(all_dates))
    end_date = parse_date(max(all_dates))

    # Rolling deques per country for document_count (past LOOKBACK days only)
    doc_deques: dict[str, deque] = {c: deque(maxlen=LOOKBACK) for c in all_countries}

    fieldnames = [
        "date",
        "breadth_high_news_count",
        "breadth_neg_tone_count",
        "breadth_high_news_frac",
        "breadth_neg_tone_frac",
        "breadth_countries_active",
    ]

    with output_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()

        for current_date in daterange(start_date, end_date):
            date_key = format_date(current_date)
            high_news = 0
            neg_tone = 0
            active = 0

            for country in all_countries:
                day = daily[country].get(date_key)
                past = doc_deques[country]

                if day:
                    active += 1
                    if day["tone"] < 0:
                        neg_tone += 1
                    # above own rolling median only if we have enough past observations
                    if len(past) >= MIN_OBS and day["doc_count"] > rolling_median(past):
                        high_news += 1

                # update deque AFTER computing flag (no future leakage)
                doc_deques[country].append(day["doc_count"] if day else 0.0)

            writer.writerow({
                "date": date_key,
                "breadth_high_news_count": high_news,
                "breadth_neg_tone_count": neg_tone,
                "breadth_high_news_frac": round(high_news / active, 6) if active else 0.0,
                "breadth_neg_tone_frac": round(neg_tone / active, 6) if active else 0.0,
                "breadth_countries_active": active,
            })

    print(f"Input:  {input_path.resolve()}")
    print(f"Output: {output_path.resolve()}")
    print(f"Dates:  {format_date(start_date)} to {format_date(end_date)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

