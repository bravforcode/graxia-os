"""Tests for Task 11 — Dukascopy bi5 (LZMA) tick worker. Synthetic bi5
fixture bytes; no network (parse + unsupported-symbol paths only)."""

from __future__ import annotations

import lzma
import struct

from data_pipeline.backfill import dukascopy


def _make_bi5(hour_msc: int, ticks=((0, 2300000000000, 2300200000000, 1, 2),)) -> bytes:
    payload = b"".join(struct.pack("<5I", *t) for t in ticks)
    return lzma.compress(payload)


def test_parse_bi5_5_digit_scale():
    """bi5 stores prices scaled by 1e5 as uint32 (XAUUSD 2300.00 ->
    230000000). The 1e12 scale from the plan draft cannot fit uint32."""
    hour_msc = 1764864000000  # 2026-08-04T00:00:00Z
    raw = lzma.decompress(_make_bi5(hour_msc, ((0, 230000000, 230020000, 1, 2), (1000, 230010000, 230030000, 3, 4))))
    ticks = dukascopy._parse_bi5(raw, hour_msc)
    assert len(ticks) == 2
    assert ticks[0]["time_msc"] == hour_msc
    assert ticks[0]["bid"] == 2300.00
    assert ticks[0]["ask"] == 2300.20
    assert ticks[1]["time_msc"] == hour_msc + 1000
    assert ticks[1]["bid"] == 2300.10


def test_fetch_ticks_skips_unsupported_symbol(tmp_path):
    assert dukascopy.fetch_ticks("BTCUSD", "2026-08-01", "2026-08-01", tmp_path) == []
