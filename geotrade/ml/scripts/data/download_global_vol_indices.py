#!/usr/bin/env python3
"""
Download VIX and VXEEM daily closes from Yahoo Finance.
Saved in the same CSV format as other market files so the pipeline can read them.
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

SYMBOLS = ["^VIX"]


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


def to_unix(d: dt.date) -> int:
    return int(dt.datetime(d.year, d.month, d.day).timestamp())


def fetch_symbol(symbol: str, start: dt.date, end: dt.date) -> list[dict[str, str]]:
    params = urlencode({
        "period1": to_unix(start),
        "period2": to_unix(end + dt.timedelta(days=1)),
        "interval": "1d",
        "events": "history",
    })
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}?{params}"
    payload = json.loads(fetch_text(url))
    result = payload["chart"]["result"][0]
    timestamps = result.get("timestamp", [])
    closes = result["indicators"]["quote"][0]["close"]

    rows = []
    for ts, close in zip(timestamps, closes):
        if close is None:
            continue
        rows.append({
            "Date": dt.datetime.utcfromtimestamp(ts).date().strftime("%Y-%m-%d"),
            "Close": f"{close:.6f}",
        })
    return rows


def main() -> int:
    parser = argparse.ArgumentParser(description="Download VIX and VXEEM to the market_raw directory.")
    parser.add_argument("--output-dir", default="ml/data/working/market_raw")
    parser.add_argument("--start-date", default="2024-01-01")
    parser.add_argument("--end-date", default=dt.date.today().strftime("%Y-%m-%d"))
    args = parser.parse_args()

    start = dt.datetime.strptime(args.start_date, "%Y-%m-%d").date()
    end = dt.datetime.strptime(args.end_date, "%Y-%m-%d").date()
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    for symbol in SYMBOLS:
        print(f"[download] {symbol}")
        rows = fetch_symbol(symbol, start, end)
        if not rows:
            print(f"[warn] No data for {symbol}")
            continue
        filename = symbol.replace("^", "") + ".csv"
        path = output_dir / filename
        with path.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=["Date", "Close"])
            writer.writeheader()
            writer.writerows(rows)
        print(f"  -> {path} ({len(rows)} rows)")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())

