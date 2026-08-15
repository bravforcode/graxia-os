"""Fetch FX carry rate series (trial 3008) into data/fred/daily/.

Series: EUR 3M interbank (IR3TIB01EEM156N), JPY 3M (IR3TIB01JPM156N),
GBP 3M (IR3TIB01GBM156N). USD uses existing DGS3MO/DFF.
"""

import csv
import json
import os
import urllib.request
from pathlib import Path

KEY = os.environ["FRED_API_KEY"]
BASE = "https://api.stlouisfed.org/fred/series/observations"
OUT = Path(__file__).resolve().parent.parent / "data" / "fred" / "daily"

SERIES = {
    "IR3TIB01EEM156N": "EUR 3M interbank (carry trial 3008)",
    "IR3TIB01JPM156N": "JPY 3M interbank (carry trial 3008)",
    "IR3TIB01GBM156N": "GBP 3M interbank (carry trial 3008)",
}


def fetch(sid: str, start: str = "2004-01-01") -> list[dict]:
    url = f"{BASE}?series_id={sid}&api_key={KEY}&file_type=json&observation_start={start}"
    with urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": "x"}), timeout=60) as resp:
        return json.loads(resp.read().decode()).get("observations", [])


def save(sid: str, obs: list[dict]) -> int:
    path = OUT / f"{sid}.csv"
    rows = 0
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["date", "value"])
        for o in obs:
            if o.get("value", ".") != ".":
                w.writerow([o["date"], o["value"]])
                rows += 1
    return rows


if __name__ == "__main__":
    OUT.mkdir(parents=True, exist_ok=True)
    for sid, desc in SERIES.items():
        obs = fetch(sid)
        n = save(sid, obs)
        first = obs[0]["date"] if obs else "-"
        last = obs[-1]["date"] if obs else "-"
        print(f"{sid}: {n} rows ({first}..{last}) — {desc}")
