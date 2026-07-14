#!/usr/bin/env python3
"""
Join country-level GDELT features with market prices and generate labels.
"""

from __future__ import annotations

import argparse
import bisect
import csv
import datetime as dt
import math
from pathlib import Path


def _sample_std(values: list[float]) -> float:
    n = len(values)
    if n < 2:
        return 0.0
    mean = sum(values) / n
    return math.sqrt(sum((v - mean) ** 2 for v in values) / (n - 1))


def parse_feature_date(value: str) -> dt.date:
    return dt.datetime.strptime(value, "%Y%m%d").date()


def format_date(value: dt.date | None) -> str:
    return value.strftime("%Y-%m-%d") if value else ""


def load_mapping(path: Path) -> dict[str, dict[str, str]]:
    with path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        return {
            row["gdelt_country_code"]: row
            for row in reader
            if row.get("enabled", "1") == "1"
        }


def load_market_series(path: Path) -> tuple[list[dt.date], list[float]]:
    dates: list[dt.date] = []
    closes: list[float] = []
    with path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        for row in reader:
            try:
                close = float(row["Close"])
            except (TypeError, ValueError):
                continue
            dates.append(dt.datetime.strptime(row["Date"], "%Y-%m-%d").date())
            closes.append(close)
    return dates, closes


def build_output_fieldnames(feature_fieldnames: list[str]) -> list[str]:
    extra = [
        "asset_symbol",
        "asset_name",
        "asset_type",
        "label_ref_market_date",
        "label_next_market_date_1d",
        "label_next_market_date_3d",
        "label_next_market_date_5d",
        "label_current_close",
        "label_next_close_1d",
        "label_next_close_3d",
        "label_return_1d",
        "label_return_3d",
        "label_up_1d",
        "label_up_3d",
        "label_realized_vol_5d",
        "label_vol_high_5d",
        "label_has_market_data",
    ]
    return feature_fieldnames + extra


def main() -> int:
    parser = argparse.ArgumentParser(description="Build market labels for GDELT country features.")
    parser.add_argument(
        "--features-file",
        default="ml/data/processed/gdelt_country_rolling_2y.csv",
        help="Country rolling feature CSV",
    )
    parser.add_argument(
        "--mapping-file",
        default="config/country_asset_mapping.csv",
        help="Country to asset mapping CSV",
    )
    parser.add_argument(
        "--market-dir",
        default="ml/data/market/raw",
        help="Directory containing downloaded market CSV files",
    )
    parser.add_argument(
        "--output-file",
        default="ml/data/processed/gdelt_country_labeled_2y.csv",
        help="Output labeled dataset CSV",
    )
    args = parser.parse_args()

    mapping = load_mapping(Path(args.mapping_file))
    market_dir = Path(args.market_dir)

    market_data: dict[str, tuple[list[dt.date], list[float]]] = {}
    for gdelt_country_code, row in mapping.items():
        asset_symbol = row["asset_symbol"]
        market_path = market_dir / f"{asset_symbol.replace('.', '_')}.csv"
        if not market_path.exists():
            continue
        market_data[gdelt_country_code] = load_market_series(market_path)

    features_path = Path(args.features_file)
    output_path = Path(args.output_file)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    with features_path.open("r", encoding="utf-8", newline="") as fin:
        reader = csv.DictReader(fin)
        fieldnames = build_output_fieldnames(reader.fieldnames or [])
        with output_path.open("w", encoding="utf-8", newline="") as fout:
            writer = csv.DictWriter(fout, fieldnames=fieldnames)
            writer.writeheader()

            for row in reader:
                country_code = row["country_code"]
                meta = mapping.get(country_code)
                dates_closes = market_data.get(country_code)

                out_row = dict(row)
                out_row.update(
                    {
                        "asset_symbol": meta["asset_symbol"] if meta else "",
                        "asset_name": meta["asset_name"] if meta else "",
                        "asset_type": meta["asset_type"] if meta else "",
                        "label_ref_market_date": "",
                        "label_next_market_date_1d": "",
                        "label_next_market_date_3d": "",
                        "label_next_market_date_5d": "",
                        "label_current_close": "",
                        "label_next_close_1d": "",
                        "label_next_close_3d": "",
                        "label_return_1d": "",
                        "label_return_3d": "",
                        "label_up_1d": "",
                        "label_up_3d": "",
                        "label_realized_vol_5d": "",
                        "label_vol_high_5d": "",
                        "label_has_market_data": "0",
                    }
                )

                if not meta or not dates_closes:
                    writer.writerow(out_row)
                    continue

                trading_dates, closes = dates_closes
                feature_date = parse_feature_date(row["date"])
                ref_index = bisect.bisect_right(trading_dates, feature_date) - 1
                if ref_index < 0:
                    writer.writerow(out_row)
                    continue

                next_1_index = ref_index + 1
                next_3_index = ref_index + 3
                if next_1_index >= len(trading_dates):
                    writer.writerow(out_row)
                    continue

                current_close = closes[ref_index]
                next_close_1d = closes[next_1_index]
                return_1d = (next_close_1d / current_close) - 1.0 if current_close else 0.0

                out_row["label_ref_market_date"] = format_date(trading_dates[ref_index])
                out_row["label_next_market_date_1d"] = format_date(trading_dates[next_1_index])
                out_row["label_current_close"] = round(current_close, 6)
                out_row["label_next_close_1d"] = round(next_close_1d, 6)
                out_row["label_return_1d"] = round(return_1d, 8)
                out_row["label_up_1d"] = "1" if return_1d > 0 else "0"
                out_row["label_has_market_data"] = "1"

                if next_3_index < len(trading_dates):
                    next_close_3d = closes[next_3_index]
                    return_3d = (next_close_3d / current_close) - 1.0 if current_close else 0.0
                    out_row["label_next_market_date_3d"] = format_date(trading_dates[next_3_index])
                    out_row["label_next_close_3d"] = round(next_close_3d, 6)
                    out_row["label_return_3d"] = round(return_3d, 8)
                    out_row["label_up_3d"] = "1" if return_3d > 0 else "0"

                next_5_index = ref_index + 5
                # Need 5 prior closes (ref_index >= 5) and 5 forward closes
                if ref_index >= 5 and next_5_index < len(trading_dates):
                    next_5d_returns = [
                        (closes[ref_index + i + 1] / closes[ref_index + i]) - 1.0
                        for i in range(5)
                    ]
                    prev_5d_returns = [
                        (closes[ref_index - 4 + i] / closes[ref_index - 5 + i]) - 1.0
                        for i in range(5)
                    ]
                    realized_vol_5d = _sample_std(next_5d_returns)
                    realized_vol_5d_prev = _sample_std(prev_5d_returns)
                    out_row["label_next_market_date_5d"] = format_date(trading_dates[next_5_index])
                    out_row["label_realized_vol_5d"] = round(realized_vol_5d, 8)
                    out_row["label_vol_high_5d"] = "1" if realized_vol_5d > realized_vol_5d_prev else "0"

                writer.writerow(out_row)

    print(f"Features: {features_path.resolve()}")
    print(f"Output: {output_path.resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

