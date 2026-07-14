#!/usr/bin/env python3
"""
Build model-ready rolling features from the country-level daily GDELT table.
"""

from __future__ import annotations

import argparse
import csv
import datetime as dt
import math
from collections import defaultdict, deque
from pathlib import Path


BASE_NUMERIC_FIELDS = [
    "document_count",
    "numarts_sum",
    "counts_mentions",
    "theme_mentions",
    "theme_unique",
    "person_mentions",
    "person_unique",
    "organization_mentions",
    "organization_unique",
    "source_mentions",
    "source_unique",
    "cameo_event_mentions",
    "avg_tone_mean",
    "avg_tone_min",
    "avg_tone_max",
]

COUNT_FIELDS = [
    "document_count",
    "numarts_sum",
    "counts_mentions",
    "theme_mentions",
    "theme_unique",
    "person_mentions",
    "person_unique",
    "organization_mentions",
    "organization_unique",
    "source_mentions",
    "source_unique",
    "cameo_event_mentions",
]

TONE_FIELDS = ["avg_tone_mean", "avg_tone_min", "avg_tone_max"]
WINDOWS = [3, 7, 14]

# Fields to z-score normalise against each country's own rolling 30-day history.
# Chosen because they capture volume, sentiment, and event intensity.
ZSCORE_FIELDS = ["document_count", "numarts_sum", "theme_mentions", "cameo_event_mentions", "avg_tone_mean"]
ZSCORE_WINDOW = 30
ZSCORE_MIN_OBS = 5  # need at least this many past days before emitting a real z-score


def parse_date(value: str) -> dt.date:
    return dt.datetime.strptime(value, "%Y%m%d").date()


def format_date(value: dt.date) -> str:
    return value.strftime("%Y%m%d")


def daterange(start_date: dt.date, end_date: dt.date):
    current = start_date
    while current <= end_date:
        yield current
        current += dt.timedelta(days=1)


def load_daily_rows(path: Path):
    rows_by_country: dict[str, dict[str, dict[str, float]]] = defaultdict(dict)
    dates: set[str] = set()
    with path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        for row in reader:
            country = row["country_code"]
            date_value = row["date"]
            dates.add(date_value)
            parsed = {"country_code": country, "date": date_value}
            for field in BASE_NUMERIC_FIELDS:
                value = row.get(field, "")
                parsed[field] = float(value) if value != "" else 0.0
            rows_by_country[country][date_value] = parsed
    return rows_by_country, dates


def _zscore(values: deque, current: float) -> float:
    """Z-score of current value relative to the deque (past observations only)."""
    n = len(values)
    if n < ZSCORE_MIN_OBS:
        return 0.0
    mean = sum(values) / n
    variance = sum((v - mean) ** 2 for v in values) / n
    std = math.sqrt(variance)
    return (current - mean) / std if std > 1e-9 else 0.0


def build_output_fieldnames():
    fieldnames = ["date", "country_code", "has_gdelt_data"]
    fieldnames.extend(BASE_NUMERIC_FIELDS)
    for field in BASE_NUMERIC_FIELDS:
        fieldnames.append(f"{field}_lag1")
    for window in WINDOWS:
        for field in COUNT_FIELDS:
            fieldnames.append(f"{field}_sum_{window}d")
        for field in TONE_FIELDS:
            fieldnames.append(f"{field}_mean_{window}d")
    for field in ZSCORE_FIELDS:
        fieldnames.append(f"{field}_zscore_{ZSCORE_WINDOW}d")
    return fieldnames


def main() -> int:
    parser = argparse.ArgumentParser(description="Build rolling country features from aggregated GDELT data.")
    parser.add_argument(
        "--input-file",
        default="ml/data/processed/gdelt_country_daily_2y.csv",
        help="Path to aggregated country daily CSV",
    )
    parser.add_argument(
        "--output-file",
        default="ml/data/processed/gdelt_country_rolling_2y.csv",
        help="Path to model-ready rolling features CSV",
    )
    args = parser.parse_args()

    input_path = Path(args.input_file)
    rows_by_country, available_dates = load_daily_rows(input_path)
    if not available_dates:
        raise SystemExit(f"No rows found in {input_path}")

    start_date = parse_date(min(available_dates))
    end_date = parse_date(max(available_dates))
    output_path = Path(args.output_file)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = build_output_fieldnames()

    with output_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()

        for country_code in sorted(rows_by_country):
            history = rows_by_country[country_code]
            lag1 = {field: 0.0 for field in BASE_NUMERIC_FIELDS}
            windows = {
                window: {field: deque(maxlen=window) for field in BASE_NUMERIC_FIELDS}
                for window in WINDOWS
            }
            zscore_windows = {field: deque(maxlen=ZSCORE_WINDOW) for field in ZSCORE_FIELDS}

            for current_date in daterange(start_date, end_date):
                date_key = format_date(current_date)
                base_row = history.get(date_key)
                has_gdelt_data = 1 if base_row else 0

                if base_row is None:
                    base_row = {"date": date_key, "country_code": country_code}
                    for field in BASE_NUMERIC_FIELDS:
                        base_row[field] = 0.0

                output_row = {
                    "date": date_key,
                    "country_code": country_code,
                    "has_gdelt_data": has_gdelt_data,
                }
                for field in BASE_NUMERIC_FIELDS:
                    output_row[field] = base_row[field]
                    output_row[f"{field}_lag1"] = lag1[field]

                for window in WINDOWS:
                    for field in COUNT_FIELDS:
                        output_row[f"{field}_sum_{window}d"] = round(sum(windows[window][field]), 6)
                    for field in TONE_FIELDS:
                        values = windows[window][field]
                        output_row[f"{field}_mean_{window}d"] = round(sum(values) / len(values), 6) if values else 0.0

                for field in ZSCORE_FIELDS:
                    z = _zscore(zscore_windows[field], base_row[field])
                    output_row[f"{field}_zscore_{ZSCORE_WINDOW}d"] = round(z, 6)

                writer.writerow(output_row)

                for field in BASE_NUMERIC_FIELDS:
                    lag1[field] = base_row[field]
                    for window in WINDOWS:
                        windows[window][field].append(base_row[field])
                for field in ZSCORE_FIELDS:
                    zscore_windows[field].append(base_row[field])

    print(f"Input: {input_path.resolve()}")
    print(f"Output: {output_path.resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

