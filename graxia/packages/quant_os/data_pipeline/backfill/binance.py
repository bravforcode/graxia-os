"""Binance Public Data worker (data.binance.vision, no auth).

Downloads monthly funding-rate zips for futures/um, verifies the sibling
.CHECKSUM, and writes per-day parquet under the out_dir. Idempotent:
existing per-day parquet files are skipped.
"""

from __future__ import annotations

import hashlib
import urllib.request
import zipfile
from datetime import date, timedelta
from pathlib import Path

import pandas as pd

BASE_URL = "https://data.binance.vision/data/futures/um/monthly/fundingRate"


def _sha256_of(path: Path) -> str:
    sha = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            sha.update(chunk)
    return sha.hexdigest()


def _download(url: str, dest: Path) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    with urllib.request.urlopen(url, timeout=60) as resp:
        dest.write_bytes(resp.read())


def _download_to_text(url: str) -> str:
    with urllib.request.urlopen(url, timeout=60) as resp:
        return resp.read().decode()


def _month_parquet_path(out_dir: Path, symbol: str, day: date) -> Path:
    return out_dir / f"{symbol}_{day.isoformat()}.parquet"


def _months_in_range(start: date, end: date) -> list[tuple[int, int]]:
    """Every (year, month) from start through end, inclusive."""
    out: list[tuple[int, int]] = []
    cur = start.replace(day=1)
    last = end.replace(day=1)
    while cur <= last:
        out.append((cur.year, cur.month))
        cur = (cur.replace(day=28) + timedelta(days=4)).replace(day=1)
    return out


def fetch_funding(
    symbol: str,
    start_date: str,
    end_date: str,
    out_dir: str | Path,
    *,
    progress_file: str | Path | None = None,
) -> list[Path]:
    out_dir = Path(out_dir)
    written: list[Path] = []
    start, end = date.fromisoformat(start_date), date.fromisoformat(end_date)
    for year, month in _months_in_range(start, end):
        zip_name = f"{symbol}-fundingRate-{year:04d}-{month:02d}.zip"
        dest_zip = out_dir / "downloads" / zip_name
        month_start = max(start, date(year, month, 1))
        month_end = min(end, date(year, month, 28) + timedelta(days=4))
        month_days = [month_start + timedelta(days=i) for i in range((month_end - month_start).days + 1)]
        if all(_month_parquet_path(out_dir, symbol, d).exists() for d in month_days):
            continue  # month already fully backfilled — skip download entirely
        dest_zip.parent.mkdir(parents=True, exist_ok=True)
        if not dest_zip.exists():
            url = f"{BASE_URL}/{symbol}/{zip_name}"
            _download(url, dest_zip)
        checksum_url = f"{BASE_URL}/{symbol}/{zip_name}.CHECKSUM"
        try:
            expected = _download_to_text(checksum_url).split()[0]
        except Exception:
            expected = None
        if expected and _sha256_of(dest_zip) != expected:
            dest_zip.unlink()
            raise RuntimeError(f"checksum mismatch for {dest_zip.name}")
        with zipfile.ZipFile(dest_zip) as z:
            name = next(n for n in z.namelist() if n.endswith(".csv"))
            df = pd.read_csv(z.open(name))
        df["calc_time"] = pd.to_datetime(df["calc_time"], utc=True)
        for day, group in df.groupby(df["calc_time"].dt.date):
            path = _month_parquet_path(out_dir, symbol, day)
            if path.exists():
                continue
            rows = group.sort_values("calc_time")
            rows = rows.rename(
                columns={
                    "calc_time": "timestamp_utc",
                    "lastFundingRate": "funding_rate",
                    "markPrice": "mark_price",
                }
            )
            rows["timestamp_utc"] = rows["timestamp_utc"].dt.strftime("%Y-%m-%dT%H:%M:%SZ")
            rows["time_msc"] = pd.to_datetime(rows["timestamp_utc"], utc=True).astype("int64") // 10**6
            rows["symbol"] = symbol
            rows["source"] = "binance_funding"
            path.parent.mkdir(parents=True, exist_ok=True)
            rows[["time_msc", "timestamp_utc", "symbol", "funding_rate", "mark_price", "source"]].to_parquet(
                path, index=False
            )
            written.append(path)
    return written


TRADES_BASE_URL = "https://data.binance.vision/data/futures/um/daily/trades"


def fetch_trades(symbol: str, start_date: str, end_date: str, out_dir: str | Path) -> list[Path]:
    """Daily trade CSVs -> per-day parquet. Idempotent per day."""
    out_dir = Path(out_dir)
    written: list[Path] = []
    start, end = date.fromisoformat(start_date), date.fromisoformat(end_date)
    day = start
    while day <= end:
        path = out_dir / f"{symbol}_{day.isoformat()}.parquet"
        if path.exists():
            day += timedelta(days=1)
            continue
        fname = f"{symbol}-trades-{day.isoformat()}.zip"
        dest_zip = out_dir / "downloads" / fname
        dest_zip.parent.mkdir(parents=True, exist_ok=True)
        if not dest_zip.exists():
            _download(f"{TRADES_BASE_URL}/{symbol}/{fname}", dest_zip)
        with zipfile.ZipFile(dest_zip) as z:
            name = next(n for n in z.namelist() if n.endswith(".csv"))
            df = pd.read_csv(z.open(name))
        rows = df.rename(columns={"price": "price", "qty": "quantity", "time": "time_msc"})
        rows["timestamp_utc"] = pd.to_datetime(rows["time_msc"], unit="ms", utc=True).dt.strftime("%Y-%m-%dT%H:%M:%SZ")
        rows["symbol"] = symbol
        rows["source"] = "binance_trade"
        # Trades are single-price ticks: bid == ask == price so the canonical
        # tick view projection (time_msc, symbol, bid, ask, last, volume,
        # source, data_quality) stays UNION-consistent with live ticks.
        rows["bid"] = rows["price"].astype(float)
        rows["ask"] = rows["price"].astype(float)
        rows["last"] = rows["price"].astype(float)
        rows["volume"] = rows["quantity"].astype(float)
        rows["data_quality"] = "VALID"
        path.parent.mkdir(parents=True, exist_ok=True)
        rows[
            [
                "time_msc",
                "timestamp_utc",
                "symbol",
                "bid",
                "ask",
                "last",
                "volume",
                "price",
                "quantity",
                "source",
                "data_quality",
            ]
        ].to_parquet(path, index=False)
        written.append(path)
        day += timedelta(days=1)
    return written
