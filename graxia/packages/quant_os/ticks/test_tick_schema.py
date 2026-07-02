"""Tests for tick schema and storage."""

import tempfile

from graxia.packages.quant_os.tick.tick_schema import TickRecord
from graxia.packages.quant_os.tick.tick_storage import TickStorage


def test_tick_record_creation():
    tick = TickRecord(bid=2350.50, ask=2350.80, symbol="XAUUSD")
    assert tick.bid == 2350.50
    assert tick.ask == 2350.80


def test_tick_record_validate():
    tick = TickRecord(bid=2350.50, ask=2350.80, symbol="XAUUSD", source_timestamp_utc="2026-06-22T10:00:00")
    ok, issues = tick.validate()
    assert ok


def test_tick_record_validate_fails():
    tick = TickRecord(bid=-1, ask=2350.80, symbol="XAUUSD")
    ok, issues = tick.validate()
    assert not ok
    assert any("bid" in i for i in issues)


def test_tick_record_validate_inverted():
    tick = TickRecord(bid=2350.80, ask=2350.50, symbol="XAUUSD")
    ok, issues = tick.validate()
    assert not ok
    assert any("inverted" in i for i in issues)


def test_tick_record_spread():
    tick = TickRecord(bid=2350.50, ask=2350.80, symbol="XAUUSD")
    tick.compute_spread()
    assert abs(tick.spread_price - 0.30) < 1e-10


def test_tick_record_hash():
    tick = TickRecord(bid=2350.50, ask=2350.80, symbol="XAUUSD")
    tick.compute_hashes()
    assert tick.raw_payload_hash  # non-empty


def test_tick_storage_store_and_read():
    with tempfile.TemporaryDirectory() as tmp:
        storage = TickStorage(tmp)
        tick = {"bid": 2350.50, "ask": 2350.80, "symbol": "XAUUSD", "source_timestamp_utc": "2026-06-22T10:00:00"}
        storage.store_tick(tick, "mt5", "MetaQuotes-Demo", "XAUUSD")
        ticks = storage.read_ticks("mt5", "MetaQuotes-Demo", "XAUUSD", "2026-06-22")
        assert len(ticks) == 1
        assert ticks[0]["bid"] == 2350.50


def test_tick_storage_verify():
    with tempfile.TemporaryDirectory() as tmp:
        storage = TickStorage(tmp)
        tick = {"bid": 2350.50, "ask": 2350.80, "symbol": "XAUUSD", "source_timestamp_utc": "2026-06-22T10:00:00"}
        storage.store_tick(tick, "mt5", "MetaQuotes-Demo", "XAUUSD")
        storage.write_manifest("mt5", "MetaQuotes-Demo", "XAUUSD", "2026-06-22", 1)
        ok, msg = storage.verify_partition("mt5", "MetaQuotes-Demo", "XAUUSD", "2026-06-22")
        assert ok
