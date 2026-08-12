"""
sources/macro_data.py — Macro Economic Data Sources (FRED, fredapi)
"""
import pandas as pd
from datetime import datetime
from pathlib import Path
import json
import time
import sys
sys.path.insert(0, str(Path(__file__).parent.parent))
from config import FRED_API_KEY, FRED_SERIES, RETRY_MAX, RETRY_DELAY, STORAGE_DIR

MACRO_CACHE_FILE = STORAGE_DIR / "macro_cache.json"


def _load_macro_cache() -> dict:
    if MACRO_CACHE_FILE.exists():
        try:
            return json.loads(MACRO_CACHE_FILE.read_text())
        except Exception:
            pass
    return {}


def _save_macro_cache(data: dict):
    MACRO_CACHE_FILE.parent.mkdir(parents=True, exist_ok=True)
    MACRO_CACHE_FILE.write_text(json.dumps(data, indent=2))


def fetch_fred_series(series_id: str) -> pd.DataFrame:
    """Fetch a single FRED series with retry"""
    from fredapi import Fred
    for attempt in range(RETRY_MAX):
        try:
            fred = Fred(api_key=FRED_API_KEY)
            series = fred.get_series(series_id, observation_start="2020-01-01")
            df = pd.DataFrame({"value": series})
            df["series_id"] = series_id
            df["timestamp"] = df.index
            df["fetched_at"] = datetime.now()
            df = df.reset_index(drop=True)
            return df
        except Exception as e:
            if attempt < RETRY_MAX - 1:
                time.sleep(RETRY_DELAY)
            else:
                print(f"  FRED error {series_id}: {e}")
    return pd.DataFrame()


def fetch_all_macro_data() -> pd.DataFrame:
    """Fetch all FRED macro series with incremental loading"""
    print("=== Fetching Macro Data ===")
    cache = _load_macro_cache()
    results = []
    for series_id, description in FRED_SERIES.items():
        print(f"  {series_id}: {description}")
        last_fetched = cache.get(series_id)
        if last_fetched:
            print(f"    (last: {last_fetched[:10]})")
        df = fetch_fred_series(series_id)
        if len(df) > 0:
            results.append(df)
            cache[series_id] = datetime.now().isoformat()
    _save_macro_cache(cache)
    if results:
        combined = pd.concat(results)
        print(f"  Total: {len(combined)} rows")
        return combined
    return pd.DataFrame()
