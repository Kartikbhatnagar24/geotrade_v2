#!/usr/bin/env python3
"""
Add lagged market-context features to the engineered labeled dataset.
"""

from __future__ import annotations

import argparse
import csv
import datetime as dt
import math
from pathlib import Path


def parse_market_date(value: str) -> dt.date:
    return dt.datetime.strptime(value, "%Y-%m-%d").date()


def load_market_context(market_dir: Path) -> dict[tuple[str, str], dict[str, str]]:
    context: dict[tuple[str, str], dict[str, str]] = {}
    for market_file in market_dir.glob("*.csv"):
        asset_symbol = market_file.stem
        rows = []
        with market_file.open("r", encoding="utf-8", newline="") as handle:
            reader = csv.DictReader(handle)
            for row in reader:
                try:
                    close = float(row["Close"])
                except (TypeError, ValueError):
                    continue
                rows.append({"date": row["Date"], "close": close})

        for index, row in enumerate(rows):
            prev_1 = rows[index - 1]["close"] if index >= 1 else None
            prev_3 = rows[index - 3]["close"] if index >= 3 else None
            trailing = []
            for j in range(max(1, index - 5), index + 1):
                prev_close = rows[j - 1]["close"]
                curr_close = rows[j]["close"]
                trailing.append((curr_close / prev_close) - 1.0)

            prev_return_1d = ((row["close"] / prev_1) - 1.0) if prev_1 else 0.0
            prev_return_3d = ((row["close"] / prev_3) - 1.0) if prev_3 else 0.0
            mean_ret = sum(trailing) / len(trailing) if trailing else 0.0
            variance = sum((value - mean_ret) ** 2 for value in trailing) / len(trailing) if trailing else 0.0
            vol_5d = math.sqrt(variance) if trailing else 0.0

            context[(asset_symbol, row["date"])] = {
                "market_prev_return_1d": f"{prev_return_1d:.8f}",
                "market_prev_return_3d": f"{prev_return_3d:.8f}",
                "market_volatility_5d": f"{vol_5d:.8f}",
                "market_momentum_5d": f"{mean_ret:.8f}",
            }
    return context


def load_vol_index(path: Path) -> dict[str, dict[str, str]]:
    """Load a global vol index (VIX/VXEEM) as {date: {close, change_1d}} lookup."""
    rows: list[dict[str, str]] = []
    with path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        for row in reader:
            try:
                float(row["Close"])
            except (TypeError, ValueError):
                continue
            rows.append(row)

    result: dict[str, dict[str, str]] = {}
    for i, row in enumerate(rows):
        close = float(row["Close"])
        prev_close = float(rows[i - 1]["Close"]) if i >= 1 else close
        change_1d = (close / prev_close - 1.0) if prev_close else 0.0
        result[row["Date"]] = {
            "close": f"{close:.6f}",
            "change_1d": f"{change_1d:.8f}",
        }
    return result


def load_breadth(path: Path) -> dict[str, dict[str, str]]:
    """Load breadth features as {gdelt_date_yyyymmdd: {field: value}} lookup."""
    result: dict[str, dict[str, str]] = {}
    with path.open("r", encoding="utf-8", newline="") as handle:
        for row in csv.DictReader(handle):
            result[row["date"]] = {k: v for k, v in row.items() if k != "date"}
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description="Add market context features to the engineered labeled dataset.")
    parser.add_argument("--input-file", default="ml/data/working/gdelt_country_labeled_2y_engineered.csv")
    parser.add_argument("--market-dir", default="ml/data/working/market_raw")
    parser.add_argument("--breadth-file", default="ml/data/working/gdelt_breadth_daily.csv")
    parser.add_argument("--output-file", default="ml/data/working/gdelt_country_labeled_2y_engineered_market.csv")
    args = parser.parse_args()

    context = load_market_context(Path(args.market_dir))

    market_dir = Path(args.market_dir)
    vix_data = load_vol_index(market_dir / "VIX.csv") if (market_dir / "VIX.csv").exists() else {}
    if not vix_data:
        print("[warn] VIX.csv not found â€” run download_global_vol_indices.py first")

    breadth_path = Path(args.breadth_file)
    breadth_data = load_breadth(breadth_path) if breadth_path.exists() else {}
    if not breadth_data:
        print("[warn] breadth file not found â€” run build_breadth_features.py first")

    input_path = Path(args.input_file)
    output_path = Path(args.output_file)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    new_fields = [
        "market_prev_return_1d",
        "market_prev_return_3d",
        "market_volatility_5d",
        "market_momentum_5d",
        "vix_close",
        "vix_change_1d",
        "breadth_high_news_count",
        "breadth_neg_tone_count",
        "breadth_high_news_frac",
        "breadth_neg_tone_frac",
        "breadth_countries_active",
    ]

    with input_path.open("r", encoding="utf-8", newline="") as fin:
        reader = csv.DictReader(fin)
        fieldnames = (reader.fieldnames or []) + [field for field in new_fields if field not in (reader.fieldnames or [])]
        with output_path.open("w", encoding="utf-8", newline="") as fout:
            writer = csv.DictWriter(fout, fieldnames=fieldnames)
            writer.writeheader()
            for row in reader:
                for field in new_fields:
                    row[field] = "0"
                ref_date = row.get("label_ref_market_date", "")
                if row.get("asset_symbol") and ref_date:
                    values = context.get((row["asset_symbol"], ref_date))
                    if values:
                        row.update(values)
                if ref_date:
                    vix = vix_data.get(ref_date)
                    if vix:
                        row["vix_close"] = vix["close"]
                        row["vix_change_1d"] = vix["change_1d"]
                # breadth is keyed by GDELT date (YYYYMMDD), not market date
                gdelt_date = row.get("date", "")
                if gdelt_date:
                    breadth = breadth_data.get(gdelt_date)
                    if breadth:
                        row.update(breadth)
                writer.writerow(row)

    print(f"Output: {output_path.resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

