#!/usr/bin/env python3
"""
Download historical daily market data for mapped assets from Yahoo Finance.
"""

from __future__ import annotations

import argparse
import csv
import datetime as dt
import json
import ssl
import time
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import Request, urlopen


def parse_date(value: str) -> dt.date | None:
    if not value:
        return None
    return dt.datetime.strptime(value, "%Y-%m-%d").date()


def fetch_text(url: str) -> str:
    headers = {
        "User-Agent": "Mozilla/5.0",
        "Accept": "application/json,text/csv,text/plain,*/*",
        "Accept-Language": "en-US,en;q=0.9",
        "Connection": "keep-alive",
    }
    request = Request(url, headers=headers)
    last_error = None
    for delay in (0, 2, 5, 10):
        if delay:
            time.sleep(delay)
        try:
            with urlopen(request) as response:
                return response.read().decode("utf-8", errors="replace")
        except Exception as exc:
            last_error = exc
            try:
                context = ssl._create_unverified_context()
                with urlopen(request, context=context) as response:
                    return response.read().decode("utf-8", errors="replace")
            except Exception as inner_exc:
                last_error = inner_exc
    raise last_error


def fetch_json(url: str) -> dict:
    return json.loads(fetch_text(url))


def load_mapping(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        return [row for row in reader if row.get("enabled", "1") == "1"]


def to_unix_timestamp(value: dt.date) -> int:
    return int(dt.datetime(value.year, value.month, value.day, 0, 0, 0).timestamp())


def fetch_yahoo_rows(symbol: str, start_date: dt.date | None, end_date: dt.date | None) -> list[dict[str, str]]:
    start = start_date or dt.date(2000, 1, 1)
    end = end_date or dt.date.today()
    params = urlencode(
        {
            "period1": to_unix_timestamp(start),
            "period2": to_unix_timestamp(end + dt.timedelta(days=1)),
            "interval": "1d",
            "events": "history",
            "includeAdjustedClose": "true",
        }
    )
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}?{params}"
    payload = fetch_json(url)
    result = payload["chart"]["result"][0]
    timestamps = result.get("timestamp", [])
    quote = result["indicators"]["quote"][0]
    adjclose = result["indicators"].get("adjclose", [{}])[0].get("adjclose", [])

    rows: list[dict[str, str]] = []
    for index, ts in enumerate(timestamps):
        close = quote["close"][index]
        open_ = quote["open"][index]
        high = quote["high"][index]
        low = quote["low"][index]
        volume = quote["volume"][index]
        if close is None:
            continue
        trade_date = dt.datetime.utcfromtimestamp(ts).date().strftime("%Y-%m-%d")
        adj = adjclose[index] if index < len(adjclose) and adjclose[index] is not None else close
        rows.append(
            {
                "Date": trade_date,
                "Open": f"{open_:.6f}" if open_ is not None else "",
                "High": f"{high:.6f}" if high is not None else "",
                "Low": f"{low:.6f}" if low is not None else "",
                "Close": f"{close:.6f}",
                "Adj Close": f"{adj:.6f}",
                "Volume": str(int(volume)) if volume is not None else "",
            }
        )
    return rows


def main() -> int:
    parser = argparse.ArgumentParser(description="Download market data from Stooq for configured country assets.")
    parser.add_argument(
        "--mapping-file",
        default="config/country_asset_mapping.csv",
        help="CSV mapping of countries to asset symbols",
    )
    parser.add_argument(
        "--output-dir",
        default="ml/data/market/raw",
        help="Directory for downloaded CSV files",
    )
    parser.add_argument("--start-date", help="Optional YYYY-MM-DD filter")
    parser.add_argument("--end-date", help="Optional YYYY-MM-DD filter")
    args = parser.parse_args()

    start_date = parse_date(args.start_date) if args.start_date else None
    end_date = parse_date(args.end_date) if args.end_date else None

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    mappings = load_mapping(Path(args.mapping_file))
    for mapping in mappings:
        if mapping.get("data_source") != "yahoo":
            continue

        symbol = mapping["asset_symbol"]
        print(f"[download] {mapping['gdelt_country_code']} -> {mapping['asset_symbol']}")
        rows = fetch_yahoo_rows(symbol, start_date, end_date)
        if not rows:
            print(f"[warn] No rows returned for {mapping['asset_symbol']}")
            continue

        output_path = output_dir / f"{mapping['asset_symbol'].replace('.', '_')}.csv"
        with output_path.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=rows[0].keys())
            writer.writeheader()
            writer.writerows(rows)

    print(f"Done. Output directory: {output_dir.resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

