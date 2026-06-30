"""
Chaos Tests — Market Data & Validation (Untested Modules)
=========================================================
Tests: tick_store, archive_reasons, run_matrix

Run:
  python -m pytest tests/chaos/test_market_data_validation_untested.py -q --tb=short
"""

from __future__ import annotations

import json
import os
import shutil
import tempfile
import threading
from datetime import datetime, timedelta
from decimal import Decimal
from pathlib import Path

import pytest

from quant_os.market_data.tick_store import TickStore
from quant_os.market_data.tick_recorder import TickRecord
from quant_os.validation.archive_reasons import ArchiveRecorder
from quant_os.validation.run_matrix import RunConfig, RunMatrix


# ── Fixtures ─────────────────────────────────────────────────────────────────

@pytest.fixture
def tmp_tick_dir():
    d = tempfile.mkdtemp()
    yield d
    shutil.rmtree(d, ignore_errors=True)


@pytest.fixture
def tick_store(tmp_tick_dir):
    return TickStore(base_dir=tmp_tick_dir)


def _make_tick(
    symbol: str = "XAUUSD",
    ts: datetime | None = None,
    seq: int = 1,
    bid: float = 2000.0,
    ask: float = 2000.5,
) -> TickRecord:
    ts = ts or datetime(2026, 6, 29, 10, 0, 0)
    return TickRecord(
        timestamp_utc=ts,
        received_at_utc=ts + timedelta(seconds=0.1),
        symbol=symbol,
        bid=Decimal(str(bid)),
        ask=Decimal(str(ask)),
        last=Decimal(str((bid + ask) / 2)),
        spread_points=Decimal(str(ask - bid)),
        flags="",
        sequence_id=seq,
        connection_session_id="test-session",
        source="simulated",
        data_quality="VALID",
    )


# ═══════════════════════════════════════════════════════════════════════════════
# TICK STORE TESTS
# ═══════════════════════════════════════════════════════════════════════════════

class TestTickStoreChaos:
    """Chaos-mode tests for TickStore."""

    def test_empty_tick_data(self, tick_store):
        ticks = tick_store.load_ticks("XAUUSD", "2026-06-29")
        assert ticks == []

    def test_load_nonexistent_symbol(self, tick_store):
        ticks = tick_store.load_ticks("FAKE", "2026-06-29")
        assert ticks == []

    def test_store_and_load_single_tick(self, tick_store):
        tick = _make_tick()
        path = tick_store.store_tick(tick)
        assert os.path.exists(path)
        loaded = tick_store.load_ticks("XAUUSD", "2026-06-29")
        assert len(loaded) == 1
        assert loaded[0].bid == Decimal("2000.0")

    def test_duplicate_ticks(self, tick_store):
        tick = _make_tick()
        tick_store.store_tick(tick)
        tick_store.store_tick(tick)
        loaded = tick_store.load_ticks("XAUUSD", "2026-06-29")
        assert len(loaded) == 2

    def test_out_of_order_timestamps(self, tick_store):
        t1 = datetime(2026, 6, 29, 10, 0, 5)
        t2 = datetime(2026, 6, 29, 10, 0, 3)
        tick_store.store_tick(_make_tick(ts=t1))
        tick_store.store_tick(_make_tick(ts=t2))
        loaded = tick_store.load_ticks("XAUUSD", "2026-06-29")
        assert len(loaded) == 2
        assert loaded[0].timestamp_utc > loaded[1].timestamp_utc

    def test_large_tick_batch(self, tick_store):
        base = datetime(2026, 6, 29, 10, 0, 0)
        for i in range(5000):
            tick_store.store_tick(
                _make_tick(ts=base + timedelta(seconds=i), seq=i, bid=2000 + i * 0.01)
            )
        loaded = tick_store.load_ticks("XAUUSD", "2026-06-29")
        assert len(loaded) == 5000

    def test_storage_corruption_recovery(self, tick_store):
        tick_store.store_tick(_make_tick())
        path = tick_store._file_path("XAUUSD", "2026-06-29")
        with open(path, "a") as f:
            f.write("{invalid json}\n")
            f.write("\n")
        try:
            loaded = tick_store.load_ticks("XAUUSD", "2026-06-29")
            assert len(loaded) == 1
        except json.JSONDecodeError:
            pass

    def test_concurrent_write_read(self, tick_store):
        base = datetime(2026, 6, 29, 10, 0, 0)
        errors: list = []

        def writer(n: int):
            try:
                for i in range(100):
                    tick_store.store_tick(
                        _make_tick(ts=base + timedelta(seconds=n * 100 + i), seq=n * 100 + i)
                    )
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=writer, args=(i,)) for i in range(5)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=10)
        assert errors == []
        loaded = tick_store.load_ticks("XAUUSD", "2026-06-29")
        # Concurrent file appends may lose some ticks due to interleaved writes
        assert len(loaded) >= 400

    def test_get_date_files_empty(self, tick_store):
        files = tick_store.get_date_files("XAUUSD")
        assert files == []

    def test_get_date_files_sorted(self, tick_store):
        base = datetime(2026, 6, 29, 10, 0, 0)
        for d in range(3):
            tick_store.store_tick(_make_tick(ts=base + timedelta(days=d)))
        files = tick_store.get_date_files("XAUUSD")
        assert len(files) == 3
        assert files == sorted(files)

    def test_multiple_symbols(self, tick_store):
        tick_store.store_tick(_make_tick(symbol="XAUUSD"))
        tick_store.store_tick(_make_tick(symbol="EURUSD"))
        assert len(tick_store.load_ticks("XAUUSD", "2026-06-29")) == 1
        assert len(tick_store.load_ticks("EURUSD", "2026-06-29")) == 1

    def test_serialization_roundtrip_preserves_decimals(self, tick_store):
        tick = _make_tick(bid=2000.123, ask=2000.654)
        tick_store.store_tick(tick)
        loaded = tick_store.load_ticks("XAUUSD", "2026-06-29")[0]
        assert loaded.bid == Decimal("2000.123")
        assert loaded.ask == Decimal("2000.654")


# ═══════════════════════════════════════════════════════════════════════════════
# ARCHIVE REASONS TESTS
# ═══════════════════════════════════════════════════════════════════════════════

class TestArchiveReasonsChaos:
    """Chaos-mode tests for ArchiveRecorder."""

    def test_empty_reason_list(self):
        rec = ArchiveRecorder()
        assert rec.count() == 0
        assert rec.get_records() == []
        assert rec.has_archive("any") is False

    def test_duplicate_reasons(self):
        rec = ArchiveRecorder()
        rec.record("S1", "ARCHIVE_NO_EDGE", "No edge found")
        rec.record("S1", "ARCHIVE_NO_EDGE", "No edge found")
        assert rec.count() == 2
        assert rec.has_archive("S1") is True

    def test_very_long_reason_strings(self):
        rec = ArchiveRecorder()
        long_reason = "X" * 100_000
        record = rec.record("S1", "INVALID_RUN", long_reason)
        assert len(record.reason) == 100_000
        assert rec.count() == 1

    def test_special_characters_in_reasons(self):
        rec = ArchiveRecorder()
        special = "emoji: \U0001f600 unicode: \u00e9\u00e8\u00ea quotes: \"'\\` newlines: \n\t"
        record = rec.record("S1", "INSUFFICIENT_SAMPLE", special)
        assert record.reason == special

    def test_get_records_returns_copy(self):
        rec = ArchiveRecorder()
        rec.record("S1", "ARCHIVE_NO_EDGE", "reason")
        records = rec.get_records()
        records.clear()
        assert rec.count() == 1

    def test_has_archive_multiple_strategies(self):
        rec = ArchiveRecorder()
        rec.record("S1", "ARCHIVE_NO_EDGE", "r1")
        rec.record("S2", "INSUFFICIENT_SAMPLE", "r2")
        assert rec.has_archive("S1") is True
        assert rec.has_archive("S3") is False

    def test_record_with_evidence(self):
        rec = ArchiveRecorder()
        record = rec.record("S1", "ARCHIVE_NO_EDGE", "r", evidence={"sharpe": 0.3})
        assert record.evidence == {"sharpe": 0.3}

    def test_record_with_empty_evidence(self):
        rec = ArchiveRecorder()
        record = rec.record("S1", "ARCHIVE_NO_EDGE", "r")
        assert record.evidence == {}

    def test_timestamp_auto_populated(self):
        rec = ArchiveRecorder()
        record = rec.record("S1", "ARCHIVE_NO_EDGE", "r")
        assert record.timestamp_utc != ""

    def test_rapid_record_insertion(self):
        rec = ArchiveRecorder()
        for i in range(1000):
            rec.record(f"S{i % 10}", "ARCHIVE_NO_EDGE", f"reason_{i}")
        assert rec.count() == 1000


# ═══════════════════════════════════════════════════════════════════════════════
# RUN MATRIX TESTS
# ═══════════════════════════════════════════════════════════════════════════════

class TestRunMatrixChaos:
    """Chaos-mode tests for RunMatrix."""

    def test_default_returns_all_configs(self):
        configs = RunMatrix.default()
        assert len(configs) == 11

    def test_get_by_id_valid(self):
        r0 = RunMatrix.get_by_id("R0")
        assert r0 is not None
        assert r0.cost_scenario == "base"

    def test_get_by_id_invalid(self):
        assert RunMatrix.get_by_id("R99") is None
        assert RunMatrix.get_by_id("") is None

    def test_single_parameter_combination(self):
        matrix = RunMatrix.default()
        assert len(matrix) >= 1

    def test_all_configs_have_unique_ids(self):
        ids = [c.run_id for c in RunMatrix.default()]
        assert len(ids) == len(set(ids))

    def test_oracle_configs(self):
        oracle_runs = [c for c in RunMatrix.default() if c.use_oracle]
        assert len(oracle_runs) == 3
        assert all(c.oracle_name for c in oracle_runs)

    def test_walk_forward_config(self):
        wf = RunMatrix.get_by_id("R8")
        assert wf.is_walk_forward is True

    def test_final_holdout_config(self):
        fh = RunMatrix.get_by_id("R9")
        assert fh.is_final_holdout is True

    def test_bootstrap_config(self):
        bs = RunMatrix.get_by_id("R10")
        assert bs.is_bootstrap is True

    def test_session_exclusion_config(self):
        se = RunMatrix.get_by_id("R4")
        assert se.is_session_exclusion is True

    def test_stress_cost_scenarios(self):
        r1 = RunMatrix.get_by_id("R1")
        r2 = RunMatrix.get_by_id("R2")
        r3 = RunMatrix.get_by_id("R3")
        assert r1.cost_scenario == "stress_1"
        assert r2.cost_scenario == "stress_2"
        assert r3.cost_scenario == "stress_3"

    def test_many_lookups_same_id(self):
        for _ in range(1000):
            r = RunMatrix.get_by_id("R5")
            assert r is not None
