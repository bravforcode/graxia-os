"""FRED API wrapper with rate limiting, caching, and series catalog."""

import os
import time
from pathlib import Path
from typing import Optional

import pandas as pd
import requests
from dotenv import load_dotenv

load_dotenv()

FRED_BASE = "https://api.stlouisfed.org/fred/series/observations"

SERIES_CATALOG = {
    "DFII10": "10-Year Treasury Inflation-Indexed Security, Constant Maturity (real yield)",
    "VIXCLS": "CBOE Volatility Index: VIX",
    "DCOILWTICO": "Crude Oil Prices: West Texas Intermediate (WTI)",
    "GVZCLS": "CBOE Gold ETF Volatility Index",
    "T10YIE": "10-Year Breakeven Inflation Rate",
    "DGS10": "10-Year Treasury Constant Maturity Rate",
    "DTWEXBGS": "Trade Weighted U.S. Dollar Index: Broad, Goods and Services",
    "UNRATE": "Unemployment Rate",
    "FEDFUNDS": "Federal Funds Effective Rate",
}

DEFAULT_CACHE_DIR = Path("data/macro")
MAX_RPM = 120
MIN_INTERVAL = 60.0 / MAX_RPM


class FredClient:
    def __init__(self, api_key: Optional[str] = None, cache_dir: Optional[Path] = None):
        self._api_key = api_key or os.getenv("FRED_API_KEY") or ""
        if not self._api_key:
            raise ValueError("FRED_API_KEY not set. Provide api_key or set env var FRED_API_KEY.")
        self._cache_dir = cache_dir or DEFAULT_CACHE_DIR
        self._cache_dir.mkdir(parents=True, exist_ok=True)
        self._last_call: float = 0.0

    @property
    def catalog(self) -> dict:
        return dict(SERIES_CATALOG)

    def _rate_limit(self) -> None:
        elapsed = time.monotonic() - self._last_call
        if elapsed < MIN_INTERVAL:
            time.sleep(MIN_INTERVAL - elapsed)
        self._last_call = time.monotonic()

    def _cache_path(self, series_id: str, start_date: str, end_date: str) -> Path:
        safe = f"{series_id}_{start_date}_{end_date}.parquet"
        return self._cache_dir / safe

    def _cache_load(self, series_id: str, start_date: str, end_date: str) -> Optional[pd.Series]:
        path = self._cache_path(series_id, start_date, end_date)
        if not path.exists():
            return None
        try:
            df = pd.read_parquet(path)
            if df.empty:
                return None
            s = df.set_index(df.columns[0])[df.columns[1]]
            s.index = pd.to_datetime(s.index)
            s.name = series_id
            return s
        except Exception:
            return None

    def _cache_save(self, series: pd.Series, series_id: str, start_date: str, end_date: str) -> None:
        path = self._cache_path(series_id, start_date, end_date)
        df = series.reset_index()
        df.columns = ["date", "value"]
        df.to_parquet(path, index=False)

    def fetch_series(
        self,
        series_id: str,
        start_date: str,
        end_date: str,
        force: bool = False,
    ) -> pd.Series:
        if not force:
            cached = self._cache_load(series_id, start_date, end_date)
            if cached is not None:
                return cached

        self._rate_limit()
        params = {
            "series_id": series_id,
            "api_key": self._api_key,
            "file_type": "json",
            "observation_start": start_date,
            "observation_end": end_date,
            "sort_order": "asc",
        }
        try:
            resp = requests.get(FRED_BASE, params=params, timeout=30)
            resp.raise_for_status()
            data = resp.json()
        except requests.RequestException as e:
            raise RuntimeError(f"FRED API request failed for {series_id}: {e}") from e

        observations = data.get("observations", [])
        if not observations:
            return pd.Series(dtype=float, name=series_id)

        records = []
        for obs in observations:
            val = obs.get("value", ".")
            if val == ".":
                continue
            records.append((pd.Timestamp(obs["date"]), float(val)))

        if not records:
            return pd.Series(dtype=float, name=series_id)

        dates, values = zip(*records)
        result = pd.Series(values, index=pd.DatetimeIndex(dates), name=series_id, dtype=float)
        result = result.sort_index()
        self._cache_save(result, series_id, start_date, end_date)
        return result

    def fetch_release(
        self,
        release_id: str,
        start_date: str,
        end_date: str,
    ) -> pd.DataFrame:
        self._rate_limit()
        url = "https://api.stlouisfed.org/fred/release/series"
        params = {
            "release_id": release_id,
            "api_key": self._api_key,
            "file_type": "json",
        }
        try:
            resp = requests.get(url, params=params, timeout=30)
            resp.raise_for_status()
            data = resp.json()
        except requests.RequestException as e:
            raise RuntimeError(f"FRED release request failed for {release_id}: {e}") from e

        series_list = data.get("seriess", [])
        if not series_list:
            return pd.DataFrame()

        all_series = {}
        for entry in series_list:
            sid = entry["id"]
            try:
                s = self.fetch_series(sid, start_date, end_date)
                if not s.empty and len(s) > 0:
                    all_series[sid] = s
            except Exception:
                continue

        if not all_series:
            return pd.DataFrame()

        df = pd.DataFrame(all_series)
        df.index = pd.to_datetime(df.index)
        return df.sort_index()

    def fetch_multiple(
        self,
        series_ids: list[str],
        start_date: str,
        end_date: str,
        silent: bool = False,
    ) -> pd.DataFrame:
        all_series = {}
        for sid in series_ids:
            try:
                s = self.fetch_series(sid, start_date, end_date)
                if not s.empty and len(s) > 0:
                    all_series[sid] = s
            except Exception as e:
                if not silent:
                    print(f"Warning: failed to fetch {sid}: {e}")
        if not all_series:
            return pd.DataFrame()
        df = pd.DataFrame(all_series)
        df.index = pd.to_datetime(df.index)
        return df.sort_index()
