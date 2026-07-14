#!/usr/bin/env python3
"""
Build a first-pass engineered feature table from the labeled working dataset.
"""

from __future__ import annotations

import argparse
import csv
from pathlib import Path


BASE_RATIO_SPECS = [
    ("document_count", "document_count_sum_14d", "document_count_vs_14d"),
    ("theme_mentions", "theme_mentions_sum_14d", "theme_mentions_vs_14d"),
    ("person_mentions", "person_mentions_sum_14d", "person_mentions_vs_14d"),
    ("organization_mentions", "organization_mentions_sum_14d", "organization_mentions_vs_14d"),
    ("cameo_event_mentions", "cameo_event_mentions_sum_14d", "cameo_event_mentions_vs_14d"),
]

PER_DOC_SPECS = [
    ("theme_mentions", "theme_mentions_per_doc"),
    ("theme_unique", "theme_unique_per_doc"),
    ("person_mentions", "person_mentions_per_doc"),
    ("person_unique", "person_unique_per_doc"),
    ("organization_mentions", "organization_mentions_per_doc"),
    ("organization_unique", "organization_unique_per_doc"),
    ("source_mentions", "source_mentions_per_doc"),
    ("source_unique", "source_unique_per_doc"),
    ("cameo_event_mentions", "cameo_event_mentions_per_doc"),
]

DELTA_SPECS = [
    ("document_count", "document_count_lag1", "document_count_delta_1d"),
    ("theme_mentions", "theme_mentions_lag1", "theme_mentions_delta_1d"),
    ("person_mentions", "person_mentions_lag1", "person_mentions_delta_1d"),
    ("organization_mentions", "organization_mentions_lag1", "organization_mentions_delta_1d"),
    ("cameo_event_mentions", "cameo_event_mentions_lag1", "cameo_event_mentions_delta_1d"),
    ("avg_tone_mean", "avg_tone_mean_lag1", "avg_tone_mean_delta_1d"),
    ("avg_tone_min", "avg_tone_min_lag1", "avg_tone_min_delta_1d"),
    ("avg_tone_max", "avg_tone_max_lag1", "avg_tone_max_delta_1d"),
]

TREND_SPECS = [
    ("document_count_sum_3d", "document_count_sum_14d", "document_count_3d_vs_14d"),
    ("theme_mentions_sum_3d", "theme_mentions_sum_14d", "theme_mentions_3d_vs_14d"),
    ("person_mentions_sum_3d", "person_mentions_sum_14d", "person_mentions_3d_vs_14d"),
    ("organization_mentions_sum_3d", "organization_mentions_sum_14d", "organization_mentions_3d_vs_14d"),
    ("cameo_event_mentions_sum_3d", "cameo_event_mentions_sum_14d", "cameo_event_mentions_3d_vs_14d"),
    ("avg_tone_mean_mean_3d", "avg_tone_mean_mean_14d", "avg_tone_mean_3d_minus_14d"),
]


def to_float(row: dict[str, str], key: str) -> float:
    value = row.get(key, "")
    if value == "":
        return 0.0
    try:
        return float(value)
    except ValueError:
        return 0.0


def safe_ratio(numerator: float, denominator: float) -> float:
    if denominator == 0:
        return 0.0
    return numerator / denominator


def rounded(value: float) -> str:
    return f"{value:.8f}"


def build_fieldnames(base_fieldnames: list[str]) -> list[str]:
    engineered = [name for _, _, name in BASE_RATIO_SPECS]
    engineered.extend(name for _, name in PER_DOC_SPECS)
    engineered.extend(name for _, _, name in DELTA_SPECS)
    engineered.extend(name for _, _, name in TREND_SPECS)
    engineered.extend(
        [
            "source_diversity_ratio",
            "organization_diversity_ratio",
            "person_diversity_ratio",
            "theme_density_14d",
            "news_intensity_14d",
            "tone_range",
            "tone_range_14d",
        ]
    )
    return base_fieldnames + engineered


def main() -> int:
    parser = argparse.ArgumentParser(description="Engineer first-pass market prediction features.")
    parser.add_argument(
        "--input-file",
        default="ml/data/working/gdelt_country_labeled_2y_working.csv",
        help="Input labeled working dataset",
    )
    parser.add_argument(
        "--output-file",
        default="ml/data/working/gdelt_country_labeled_2y_engineered.csv",
        help="Output engineered dataset",
    )
    args = parser.parse_args()

    input_path = Path(args.input_file)
    output_path = Path(args.output_file)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    with input_path.open("r", encoding="utf-8", newline="") as fin:
        reader = csv.DictReader(fin)
        fieldnames = build_fieldnames(reader.fieldnames or [])
        with output_path.open("w", encoding="utf-8", newline="") as fout:
            writer = csv.DictWriter(fout, fieldnames=fieldnames)
            writer.writeheader()

            for row in reader:
                out_row = dict(row)

                for numerator_key, denominator_key, feature_name in BASE_RATIO_SPECS:
                    numerator = to_float(row, numerator_key)
                    denominator = to_float(row, denominator_key)
                    out_row[feature_name] = rounded(safe_ratio(numerator * 14.0, denominator))

                document_count = to_float(row, "document_count")
                for numerator_key, feature_name in PER_DOC_SPECS:
                    numerator = to_float(row, numerator_key)
                    out_row[feature_name] = rounded(safe_ratio(numerator, document_count))

                for current_key, lag_key, feature_name in DELTA_SPECS:
                    current_value = to_float(row, current_key)
                    lag_value = to_float(row, lag_key)
                    out_row[feature_name] = rounded(current_value - lag_value)

                for short_key, long_key, feature_name in TREND_SPECS:
                    short_value = to_float(row, short_key)
                    long_value = to_float(row, long_key)
                    if feature_name.endswith("_minus_14d"):
                        out_row[feature_name] = rounded(short_value - long_value)
                    else:
                        out_row[feature_name] = rounded(safe_ratio(short_value * (14.0 / 3.0), long_value))

                out_row["source_diversity_ratio"] = rounded(
                    safe_ratio(to_float(row, "source_unique"), to_float(row, "source_mentions"))
                )
                out_row["organization_diversity_ratio"] = rounded(
                    safe_ratio(to_float(row, "organization_unique"), to_float(row, "organization_mentions"))
                )
                out_row["person_diversity_ratio"] = rounded(
                    safe_ratio(to_float(row, "person_unique"), to_float(row, "person_mentions"))
                )
                out_row["theme_density_14d"] = rounded(
                    safe_ratio(to_float(row, "theme_mentions_sum_14d"), to_float(row, "document_count_sum_14d"))
                )
                out_row["news_intensity_14d"] = rounded(
                    safe_ratio(to_float(row, "numarts_sum_sum_14d"), to_float(row, "document_count_sum_14d"))
                )
                out_row["tone_range"] = rounded(to_float(row, "avg_tone_max") - to_float(row, "avg_tone_min"))
                out_row["tone_range_14d"] = rounded(
                    to_float(row, "avg_tone_max_mean_14d") - to_float(row, "avg_tone_min_mean_14d")
                )

                writer.writerow(out_row)

    print(f"Input: {input_path.resolve()}")
    print(f"Output: {output_path.resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

