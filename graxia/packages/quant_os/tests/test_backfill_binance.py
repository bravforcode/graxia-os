"""Tests for Task 9 — Binance funding-rates backfill worker (fixture CSVs,
no network: _download / _sha256_of / _download_to_text are monkeypatched)."""

from __future__ import annotations

import zipfile
from pathlib import Path

import pandas as pd

from data_pipeline.backfill import binance as binance_mod


def _make_month_zip(path: Path, csv_text: str):
    with zipfile.ZipFile(path, "w") as z:
        z.writestr("funding.csv", csv_text)


def test_funding_csv_to_parquet(tmp_path, monkeypatch):
    month_dir = tmp_path / "src" / "2026-08"
    month_dir.mkdir(parents=True)
    csv_text = (
        "calc_time,fundingIntervalHours,lastFundingRate,markPrice\n"
        "2026-08-01 00:00:00,8,0.0001,100.0\n"
        "2026-08-01 08:00:00,8,0.0002,101.0\n"
    )
    _make_month_zip(month_dir / "BTCUSDT-fundingRate-2026-08.zip", csv_text)
    (month_dir / "BTCUSDT-fundingRate-2026-08.zip.CHECKSUM").write_text(
        "hash_of_zip  BTCUSDT-fundingRate-2026-08.zip\n"
    )

    captured = {}

    def fake_download(url, dest):
        captured["url"] = url
        dest.write_bytes((month_dir / "BTCUSDT-fundingRate-2026-08.zip").read_bytes())

    monkeypatch.setattr(binance_mod, "_download", fake_download)
    monkeypatch.setattr(binance_mod, "_sha256_of", lambda p: "hash_of_zip")  # matches checksum
    monkeypatch.setattr(binance_mod, "_download_to_text", lambda url: "hash_of_zip  BTCUSDT-fundingRate-2026-08.zip\n")

    out = tmp_path / "out"
    paths = binance_mod.fetch_funding("BTCUSDT", "2026-08-01", "2026-08-31", out)
    assert len(paths) == 1
    df = pd.read_parquet(paths[0])
    assert len(df) == 2
    assert df.iloc[0]["source"] == "binance_funding"
    assert df.iloc[0]["funding_rate"] == 0.0001


def test_funding_idempotent_skips_existing(tmp_path, monkeypatch):
    out = tmp_path / "out"
    existing = out / "BTCUSDT_2026-08-01.parquet"
    existing.parent.mkdir(parents=True, exist_ok=True)
    existing.write_bytes(b"already-done")
    monkeypatch.setattr(binance_mod, "_download", lambda url, dest: None)  # must not be called
    monkeypatch.setattr(binance_mod, "_download_to_text", lambda url: "hash_of_zip  BTCUSDT-fundingRate-2026-08.zip\n")
    paths = binance_mod.fetch_funding("BTCUSDT", "2026-08-01", "2026-08-01", out)
    assert paths == []


def test_funding_full_month_range(tmp_path, monkeypatch):
    """Range spanning three months must iterate every month, not just the
    start/end months (plan draft only collected {start, end} months)."""
    month_dir = tmp_path / "src"
    month_dir.mkdir(parents=True)
    captured = []

    def fake_download(url, dest):
        captured.append(url)
        stem = url.rsplit("/", 1)[1].replace(".zip", "")  # "BTCUSDT-fundingRate-2026-09"
        ym = "-".join(stem.split("-")[-2:])  # "2026-09"
        csv_text = "calc_time,fundingIntervalHours,lastFundingRate,markPrice\n" f"{ym}-01 00:00:00,8,0.0001,100.0\n"
        _make_month_zip(dest, csv_text)

    monkeypatch.setattr(binance_mod, "_download", fake_download)
    monkeypatch.setattr(binance_mod, "_sha256_of", lambda p: "h")
    monkeypatch.setattr(binance_mod, "_download_to_text", lambda url: "h  x.zip\n")

    paths = binance_mod.fetch_funding("BTCUSDT", "2026-08-01", "2026-10-31", tmp_path / "out")
    assert len(paths) == 3  # Aug, Sep, Oct — not just Aug+Oct
    assert "2026-09" in captured[1]


def test_trades_csv_to_parquet(tmp_path, monkeypatch):
    src = tmp_path / "src" / "BTCUSDT-trades-2026-08-01.zip"
    src.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(src, "w") as z:
        z.writestr(
            "trades.csv",
            "id,price,qty,quoteQty,time,isBuyerMaker,isBestMatch\n" "1,100.0,0.5,50.0,1764864000000,False,True\n",
        )
    monkeypatch.setattr(binance_mod, "_download", lambda url, dest: dest.write_bytes(src.read_bytes()))
    out = tmp_path / "out"
    paths = binance_mod.fetch_trades("BTCUSDT", "2026-08-01", "2026-08-01", out)
    assert len(paths) == 1
    df = pd.read_parquet(paths[0])
    assert len(df) == 1
    assert df.iloc[0]["source"] == "binance_trade"
    assert df.iloc[0]["price"] == 100.0


def test_trades_idempotent_skips_existing(tmp_path, monkeypatch):
    out = tmp_path / "out"
    existing = out / "BTCUSDT_2026-08-01.parquet"
    existing.parent.mkdir(parents=True, exist_ok=True)
    existing.write_bytes(b"done")
    calls = []

    def fake_download(url, dest):
        calls.append(url)
        day = url.rsplit("-", 1)[1].replace(".zip", "")  # "2026-08-02"
        csv = "id,price,qty,quoteQty,time,isBuyerMaker,isBestMatch\n" "1,100.0,0.5,50.0,1764943200000,False,True\n"
        with zipfile.ZipFile(dest, "w") as z:
            z.writestr("trades.csv", csv)

    monkeypatch.setattr(binance_mod, "_download", fake_download)
    paths = binance_mod.fetch_trades("BTCUSDT", "2026-08-01", "2026-08-02", out)
    assert len(paths) == 1  # day 2 fetched, day 1 skipped
    assert (out / "BTCUSDT_2026-08-02.parquet").exists()
    assert len(calls) == 1 and "2026-08-01" not in calls[0]  # day 1 never downloaded
