#!/usr/bin/env python3
"""
Download GDELT daily GKG files and aggregate them into a country-level dataset
without requiring long-term storage of all raw files.
"""

from __future__ import annotations

import argparse
import csv
import datetime as dt
import io
import re
import tempfile
import zipfile
from collections import defaultdict
from pathlib import Path
from urllib.request import urlopen


BASE_URL = "http://data.gdeltproject.org/gkg/"
INDEX_PATTERN = re.compile(r'(\d{8}\.gkg\.csv\.zip)')
FIELDNAMES = [
    "date",
    "country_code",
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


def fetch_text(url: str) -> str:
    with urlopen(url) as response:
        return response.read().decode("utf-8", errors="replace")


def download_file(url: str, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    with urlopen(url) as response, destination.open("wb") as out_file:
        while True:
            chunk = response.read(64 * 1024)
            if not chunk:
                break
            out_file.write(chunk)


def split_semicolon(value: str) -> list[str]:
    return [item.strip() for item in value.split(";") if item.strip()]


def parse_locations(value: str) -> set[str]:
    countries: set[str] = set()
    for location in split_semicolon(value):
        parts = location.split("#")
        if len(parts) >= 3 and parts[2]:
            countries.add(parts[2].upper())
    return countries


def parse_tone(value: str) -> float | None:
    if not value:
        return None
    try:
        return float(value.split(",")[0])
    except (ValueError, IndexError):
        return None


def iter_rows_from_zip(zip_path: Path):
    with zipfile.ZipFile(zip_path) as zf:
        inner_names = [name for name in zf.namelist() if name.endswith(".csv")]
        if not inner_names:
            raise RuntimeError(f"No CSV found inside zip: {zip_path}")
        with zf.open(inner_names[0], "r") as raw_handle:
            text_handle = io.TextIOWrapper(raw_handle, encoding="utf-8", errors="replace", newline="")
            yield from csv.DictReader(text_handle, delimiter="\t")


def parse_date(value: str) -> dt.date:
    return dt.datetime.strptime(value, "%Y-%m-%d").date()


def daterange(start_date: dt.date, end_date: dt.date):
    current = start_date
    while current <= end_date:
        yield current
        current += dt.timedelta(days=1)


def build_feature_row(date_value: str, country_code: str, metrics: dict[str, object]) -> dict[str, object]:
    tones = metrics["tones"]
    return {
        "date": date_value,
        "country_code": country_code,
        "document_count": metrics["document_count"],
        "numarts_sum": metrics["numarts_sum"],
        "counts_mentions": metrics["counts_mentions"],
        "theme_mentions": metrics["theme_mentions"],
        "theme_unique": len(metrics["theme_unique"]),
        "person_mentions": metrics["person_mentions"],
        "person_unique": len(metrics["person_unique"]),
        "organization_mentions": metrics["organization_mentions"],
        "organization_unique": len(metrics["organization_unique"]),
        "source_mentions": metrics["source_mentions"],
        "source_unique": len(metrics["source_unique"]),
        "cameo_event_mentions": metrics["cameo_event_mentions"],
        "avg_tone_mean": round(sum(tones) / len(tones), 6) if tones else "",
        "avg_tone_min": round(min(tones), 6) if tones else "",
        "avg_tone_max": round(max(tones), 6) if tones else "",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Build a country-level GDELT GKG dataset over a date range.")
    parser.add_argument("--start-date", required=True, help="YYYY-MM-DD")
    parser.add_argument("--end-date", required=True, help="YYYY-MM-DD")
    parser.add_argument(
        "--output-file",
        default="ml/data/processed/gdelt_country_daily.csv",
        help="Final aggregated CSV output path",
    )
    parser.add_argument(
        "--cache-dir",
        default="data/raw/gdelt_gkg_cache",
        help="Optional cache directory for zip files when --keep-zips is used",
    )
    parser.add_argument(
        "--keep-zips",
        action="store_true",
        help="Keep downloaded zip files instead of deleting them after processing",
    )
    args = parser.parse_args()

    start_date = parse_date(args.start_date)
    end_date = parse_date(args.end_date)
    if end_date < start_date:
        parser.error("--end-date must be on or after --start-date")

    available = set(INDEX_PATTERN.findall(fetch_text(BASE_URL)))

    cache_dir = Path(args.cache_dir)
    cache_dir.mkdir(parents=True, exist_ok=True)
    output_path = Path(args.output_file)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=FIELDNAMES)
        writer.writeheader()
        missing_days = 0
        processed_days = 0
        written_rows = 0

        for current_date in daterange(start_date, end_date):
            file_name = f"{current_date:%Y%m%d}.gkg.csv.zip"
            if file_name not in available:
                print(f"[missing] {file_name}")
                missing_days += 1
                continue

            if args.keep_zips:
                zip_path = cache_dir / file_name
            else:
                temp_dir = Path(tempfile.mkdtemp(prefix="gdelt_gkg_"))
                zip_path = temp_dir / file_name

            if not zip_path.exists():
                print(f"[download] {file_name}")
                download_file(BASE_URL + file_name, zip_path)
            else:
                print(f"[cache] {file_name}")

            day_aggregates: dict[str, dict[str, object]] = defaultdict(
                lambda: {
                    "document_count": 0,
                    "numarts_sum": 0,
                    "counts_mentions": 0,
                    "theme_mentions": 0,
                    "theme_unique": set(),
                    "person_mentions": 0,
                    "person_unique": set(),
                    "organization_mentions": 0,
                    "organization_unique": set(),
                    "source_mentions": 0,
                    "source_unique": set(),
                    "cameo_event_mentions": 0,
                    "tones": [],
                }
            )

            for row in iter_rows_from_zip(zip_path):
                countries = parse_locations(row.get("LOCATIONS", ""))
                if not countries:
                    continue

                date_value = row.get("DATE", "")
                try:
                    numarts = int(row.get("NUMARTS", "0") or 0)
                except ValueError:
                    numarts = 0

                counts = split_semicolon(row.get("COUNTS", ""))
                themes = split_semicolon(row.get("THEMES", ""))
                persons = split_semicolon(row.get("PERSONS", ""))
                organizations = split_semicolon(row.get("ORGANIZATIONS", ""))
                sources = split_semicolon(row.get("SOURCES", ""))
                cameo_events = split_semicolon(row.get("CAMEOEVENTIDS", ""))
                tone = parse_tone(row.get("TONE", ""))

                for country_code in countries:
                    metrics = day_aggregates[country_code]
                    metrics["document_count"] += 1
                    metrics["numarts_sum"] += numarts
                    metrics["counts_mentions"] += len(counts)
                    metrics["theme_mentions"] += len(themes)
                    metrics["theme_unique"].update(themes)
                    metrics["person_mentions"] += len(persons)
                    metrics["person_unique"].update(persons)
                    metrics["organization_mentions"] += len(organizations)
                    metrics["organization_unique"].update(organizations)
                    metrics["source_mentions"] += len(sources)
                    metrics["source_unique"].update(sources)
                    metrics["cameo_event_mentions"] += len(cameo_events)
                    if tone is not None:
                        metrics["tones"].append(tone)

            day_rows = [
                build_feature_row(current_date.strftime("%Y%m%d"), country_code, metrics)
                for country_code, metrics in sorted(day_aggregates.items())
            ]
            writer.writerows(day_rows)
            written_rows += len(day_rows)
            processed_days += 1

            if not args.keep_zips:
                zip_path.unlink(missing_ok=True)
                zip_path.parent.rmdir()

    print(f"Processed days: {processed_days}")
    print(f"Missing days: {missing_days}")
    print(f"Wrote rows: {written_rows}")
    print(f"Output: {output_path.resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

