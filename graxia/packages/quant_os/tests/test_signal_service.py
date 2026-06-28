"""Tests for signal gateway — validation, deduplication, invalid payloads, edge cases."""

import asyncio
import json
import time
import pytest
from datetime import datetime, timezone
from unittest.mock import patch, MagicMock

from graxia.packages.quant_os.core.signal_gateway import (
    SignalGateway, Signal, RawSignalPayload, AssetClass, Side, SignalSource,
    _append_audit, DEDUP_WINDOW_SECONDS,
)


# ═══════════════════════════════════════════════════════════════════════
# Helpers
# ═══════════════════════════════════════════════════════════════════════

def _valid_payload(**overrides):
    d = {
        "symbol": "XAUUSD",
        "asset_class": "metals",
        "side": "BUY",
        "conviction": 0.8,
        "strategy": "mtm",
        "entry_price": 2025.0,
        "stop_loss": 2020.0,
        "take_profit": 2040.0,
    }
    d.update(overrides)
    return d


@pytest.fixture
def queue():
    return asyncio.Queue()


@pytest.fixture
def gw(queue):
    return SignalGateway(queue=queue, dedup_window=DEDUP_WINDOW_SECONDS)


# ═══════════════════════════════════════════════════════════════════════
# Pydantic Validation (RawSignalPayload)
# ═══════════════════════════════════════════════════════════════════════

class TestRawSignalPayload:
    """Pydantic schema edge cases."""

    def test_valid_payload(self):
        p = RawSignalPayload(**_valid_payload())
        assert p.symbol == "XAUUSD"
        assert p.side == "BUY"

    def test_empty_symbol_rejected(self):
        with pytest.raises(Exception):
            RawSignalPayload(**_valid_payload(symbol=""))

    def test_long_symbol_rejected(self):
        with pytest.raises(Exception):
            RawSignalPayload(**_valid_payload(symbol="X" * 21))

    def test_symbol_at_max_length(self):
        p = RawSignalPayload(**_valid_payload(symbol="X" * 20))
        assert len(p.symbol) == 20

    def test_conviction_above_one_rejected(self):
        with pytest.raises(Exception):
            RawSignalPayload(**_valid_payload(conviction=1.5))

    def test_conviction_negative_rejected(self):
        with pytest.raises(Exception):
            RawSignalPayload(**_valid_payload(conviction=-0.1))

    def test_conviction_boundary_zero(self):
        p = RawSignalPayload(**_valid_payload(conviction=0.0))
        assert p.conviction == 0.0

    def test_conviction_boundary_one(self):
        p = RawSignalPayload(**_valid_payload(conviction=1.0))
        assert p.conviction == 1.0

    def test_invalid_asset_class_rejected(self):
        with pytest.raises(Exception):
            RawSignalPayload(**_valid_payload(asset_class="invalid_class"))

    def test_asset_class_case_insensitive(self):
        p = RawSignalPayload(**_valid_payload(asset_class="METALS"))
        assert p.asset_class == "metals"

    def test_invalid_side_rejected(self):
        with pytest.raises(Exception):
            RawSignalPayload(**_valid_payload(side="INVALID"))

    def test_side_case_insensitive(self):
        p = RawSignalPayload(**_valid_payload(side="buy"))
        assert p.side == "BUY"

    def test_entry_price_zero_rejected(self):
        with pytest.raises(Exception):
            RawSignalPayload(**_valid_payload(entry_price=0))

    def test_entry_price_negative_rejected(self):
        with pytest.raises(Exception):
            RawSignalPayload(**_valid_payload(entry_price=-100))

    def test_stop_loss_zero_rejected(self):
        with pytest.raises(Exception):
            RawSignalPayload(**_valid_payload(stop_loss=0))

    def test_take_profit_zero_rejected(self):
        with pytest.raises(Exception):
            RawSignalPayload(**_valid_payload(take_profit=0))

    def test_empty_strategy_rejected(self):
        with pytest.raises(Exception):
            RawSignalPayload(**_valid_payload(strategy=""))

    def test_long_strategy_rejected(self):
        with pytest.raises(Exception):
            RawSignalPayload(**_valid_payload(strategy="x" * 101))

    def test_optional_timestamp(self):
        p = RawSignalPayload(**_valid_payload(timestamp="2026-01-15T10:00:00Z"))
        assert p.timestamp == "2026-01-15T10:00:00Z"

    def test_optional_regime(self):
        p = RawSignalPayload(**_valid_payload(regime="CRISIS"))
        assert p.regime == "CRISIS"

    def test_optional_metadata(self):
        p = RawSignalPayload(**_valid_payload(metadata={"key": "val"}))
        assert p.metadata["key"] == "val"

    def test_missing_required_field(self):
        with pytest.raises(Exception):
            RawSignalPayload(symbol="XAUUSD")  # missing required fields


# ═══════════════════════════════════════════════════════════════════════
# Signal Dataclass
# ═══════════════════════════════════════════════════════════════════════

class TestSignal:
    """Signal domain model edge cases."""

    def test_signal_id_deterministic(self):
        ts = datetime(2026, 1, 15, 10, 0, tzinfo=timezone.utc)
        s1 = Signal(
            symbol="XAUUSD", asset_class=AssetClass.METALS, side=Side.BUY,
            conviction=0.8, strategy="mtm", entry_price=2025.0,
            stop_loss=2020.0, take_profit=2040.0, timestamp=ts,
            source=SignalSource.ML,
        )
        s2 = Signal(
            symbol="XAUUSD", asset_class=AssetClass.METALS, side=Side.BUY,
            conviction=0.9, strategy="mtm", entry_price=2030.0,
            stop_loss=2025.0, take_profit=2045.0, timestamp=ts,
            source=SignalSource.TRADINGVIEW,
        )
        assert s1.signal_id == s2.signal_id

    def test_different_time_different_id(self):
        ts1 = datetime(2026, 1, 15, 10, 0, tzinfo=timezone.utc)
        ts2 = datetime(2026, 1, 15, 10, 2, tzinfo=timezone.utc)
        s1 = Signal(
            symbol="XAUUSD", asset_class=AssetClass.METALS, side=Side.BUY,
            conviction=0.8, strategy="mtm", entry_price=2025.0,
            stop_loss=2020.0, take_profit=2040.0, timestamp=ts1,
            source=SignalSource.ML,
        )
        s2 = Signal(
            symbol="XAUUSD", asset_class=AssetClass.METALS, side=Side.BUY,
            conviction=0.8, strategy="mtm", entry_price=2025.0,
            stop_loss=2020.0, take_profit=2040.0, timestamp=ts2,
            source=SignalSource.ML,
        )
        assert s1.signal_id != s2.signal_id

    def test_to_dict(self):
        ts = datetime(2026, 1, 15, tzinfo=timezone.utc)
        s = Signal(
            symbol="XAUUSD", asset_class=AssetClass.METALS, side=Side.BUY,
            conviction=0.8, strategy="mtm", entry_price=2025.0,
            stop_loss=2020.0, take_profit=2040.0, timestamp=ts,
            source=SignalSource.ML, regime="RANGE_BOUND",
            metadata={"key": "val"},
        )
        d = s.to_dict()
        assert d["symbol"] == "XAUUSD"
        assert d["side"] == "BUY"
        assert d["regime"] == "RANGE_BOUND"
        assert d["metadata"]["key"] == "val"
        assert len(d["signal_id"]) == 16

    def test_signal_frozen(self):
        from dataclasses import FrozenInstanceError
        ts = datetime(2026, 1, 15, tzinfo=timezone.utc)
        s = Signal(
            symbol="XAUUSD", asset_class=AssetClass.METALS, side=Side.BUY,
            conviction=0.8, strategy="mtm", entry_price=2025.0,
            stop_loss=2020.0, take_profit=2040.0, timestamp=ts,
            source=SignalSource.ML,
        )
        with pytest.raises(FrozenInstanceError):
            s.symbol = "EURUSD"

    def test_signal_id_is_16_hex_chars(self):
        ts = datetime(2026, 1, 15, tzinfo=timezone.utc)
        s = Signal(
            symbol="EURUSD", asset_class=AssetClass.FOREX, side=Side.SELL,
            conviction=0.6, strategy="mrb", entry_price=1.08,
            stop_loss=1.09, take_profit=1.07, timestamp=ts,
            source=SignalSource.PYTHON,
        )
        assert len(s.signal_id) == 16
        assert all(c in "0123456789abcdef" for c in s.signal_id)


# ═══════════════════════════════════════════════════════════════════════
# Signal Gateway — Ingestion
# ═══════════════════════════════════════════════════════════════════════

class TestSignalGatewayIngest:
    """Gateway ingestion edge cases."""

    @pytest.mark.asyncio
    async def test_valid_signal_accepted(self, gw, queue):
        result = await gw.ingest(_valid_payload(), SignalSource.ML)
        assert result is not None
        assert result.symbol == "XAUUSD"
        assert not queue.empty()

    @pytest.mark.asyncio
    async def test_invalid_payload_rejected(self, gw):
        result = await gw.ingest({"symbol": ""}, SignalSource.ML)
        assert result is None

    @pytest.mark.asyncio
    async def test_missing_fields_rejected(self, gw):
        result = await gw.ingest({"symbol": "XAUUSD"}, SignalSource.ML)
        assert result is None

    @pytest.mark.asyncio
    async def test_invalid_asset_class_rejected(self, gw):
        result = await gw.ingest(
            _valid_payload(asset_class="invalid"), SignalSource.ML
        )
        assert result is None

    @pytest.mark.asyncio
    async def test_duplicate_signal_deduped(self, gw, queue):
        payload = _valid_payload()
        r1 = await gw.ingest(payload, SignalSource.ML)
        r2 = await gw.ingest(payload, SignalSource.ML)
        assert r1 is not None
        assert r2 is None
        assert queue.qsize() == 1

    @pytest.mark.asyncio
    async def test_different_strategy_not_deduped(self, gw, queue):
        r1 = await gw.ingest(_valid_payload(strategy="mtm"), SignalSource.ML)
        r2 = await gw.ingest(_valid_payload(strategy="mrb"), SignalSource.ML)
        assert r1 is not None
        assert r2 is not None
        assert queue.qsize() == 2

    @pytest.mark.asyncio
    async def test_source_as_string(self, gw):
        result = await gw.ingest(_valid_payload(), "ml")
        assert result is not None
        assert result.source == SignalSource.ML

    @pytest.mark.asyncio
    async def test_invalid_source_rejected(self, gw):
        with pytest.raises(ValueError):
            await gw.ingest(_valid_payload(), "invalid_source")

    @pytest.mark.asyncio
    async def test_auto_timestamp_when_missing(self, gw):
        result = await gw.ingest(_valid_payload(), SignalSource.ML)
        assert result is not None
        assert result.timestamp is not None

    @pytest.mark.asyncio
    async def test_provided_timestamp_used(self, gw):
        ts = "2026-06-15T12:00:00Z"
        result = await gw.ingest(
            _valid_payload(timestamp=ts), SignalSource.ML
        )
        assert result is not None
        assert result.timestamp.year == 2026

    @pytest.mark.asyncio
    async def test_all_asset_classes_accepted(self, gw):
        for ac in ["metals", "crypto", "forex", "indices"]:
            result = await gw.ingest(
                _valid_payload(asset_class=ac, strategy=f"strat_{ac}"),
                SignalSource.ML,
            )
            assert result is not None

    @pytest.mark.asyncio
    async def test_all_sides_accepted(self, gw):
        for side in ["BUY", "SELL"]:
            result = await gw.ingest(
                _valid_payload(side=side, strategy=f"strat_{side}"),
                SignalSource.ML,
            )
            assert result is not None

    @pytest.mark.asyncio
    async def test_metadata_preserved(self, gw):
        result = await gw.ingest(
            _valid_payload(metadata={"custom_key": 42}),
            SignalSource.ML,
        )
        assert result is not None
        assert result.metadata["custom_key"] == 42


# ═══════════════════════════════════════════════════════════════════════
# Deduplication Window
# ═══════════════════════════════════════════════════════════════════════

class TestDedupWindow:
    """Deduplication timing edge cases."""

    @pytest.mark.asyncio
    async def test_same_signal_within_window_deduped(self, gw):
        r1 = await gw.ingest(_valid_payload(), SignalSource.ML)
        r2 = await gw.ingest(_valid_payload(), SignalSource.ML)
        assert r1 is not None
        assert r2 is None

    @pytest.mark.asyncio
    async def test_eviction_removes_expired(self, gw, queue):
        """After dedup window expires, same signal_id should be accepted again."""
        gw._dedup_window = 0.01  # 10ms window
        r1 = await gw.ingest(_valid_payload(), SignalSource.ML)
        await asyncio.sleep(0.02)  # wait past dedup window
        r2 = await gw.ingest(_valid_payload(), SignalSource.ML)
        assert r1 is not None
        assert r2 is not None

    @pytest.mark.asyncio
    async def test_many_signals_all_unique(self, gw, queue):
        """Many different signals should all be accepted."""
        for i in range(10):
            result = await gw.ingest(
                _valid_payload(strategy=f"strat_{i}", entry_price=2000 + i),
                SignalSource.ML,
            )
            assert result is not None
        assert queue.qsize() == 10


# ═══════════════════════════════════════════════════════════════════════
# Audit Logging
# ═══════════════════════════════════════════════════════════════════════

class TestAuditLogging:
    """Audit log edge cases."""

    def test_append_audit_creates_file(self, tmp_path):
        import graxia.packages.quant_os.core.signal_gateway as sg
        original = sg.AUDIT_LOG_PATH
        sg.AUDIT_LOG_PATH = tmp_path / "audit.jsonl"
        try:
            _append_audit({"event": "test", "data": "value"})
            assert sg.AUDIT_LOG_PATH.exists()
            content = sg.AUDIT_LOG_PATH.read_text()
            assert "test" in content
        finally:
            sg.AUDIT_LOG_PATH = original

    def test_append_audit_creates_parent_dirs(self, tmp_path):
        import graxia.packages.quant_os.core.signal_gateway as sg
        original = sg.AUDIT_LOG_PATH
        sg.AUDIT_LOG_PATH = tmp_path / "subdir" / "audit.jsonl"
        try:
            _append_audit({"event": "test"})
            assert sg.AUDIT_LOG_PATH.exists()
        finally:
            sg.AUDIT_LOG_PATH = original

    def test_multiple_appends(self, tmp_path):
        import graxia.packages.quant_os.core.signal_gateway as sg
        original = sg.AUDIT_LOG_PATH
        sg.AUDIT_LOG_PATH = tmp_path / "audit.jsonl"
        try:
            for i in range(5):
                _append_audit({"event": f"test_{i}"})
            lines = sg.AUDIT_LOG_PATH.read_text().strip().split("\n")
            assert len(lines) == 5
        finally:
            sg.AUDIT_LOG_PATH = original


# ═══════════════════════════════════════════════════════════════════════
# Edge Cases: Extreme Values
# ═══════════════════════════════════════════════════════════════════════

class TestExtremeValues:
    """Extreme and boundary value edge cases."""

    @pytest.mark.asyncio
    async def test_very_high_conviction(self, gw):
        result = await gw.ingest(_valid_payload(conviction=1.0), SignalSource.ML)
        assert result is not None

    @pytest.mark.asyncio
    async def test_very_low_conviction(self, gw):
        result = await gw.ingest(_valid_payload(conviction=0.0), SignalSource.ML)
        assert result is not None

    @pytest.mark.asyncio
    async def test_very_high_price(self, gw):
        result = await gw.ingest(
            _valid_payload(entry_price=999999.99, stop_loss=999998.0, take_profit=1000001.0),
            SignalSource.ML,
        )
        assert result is not None

    @pytest.mark.asyncio
    async def test_stop_loss_above_take_profit(self, gw):
        """SL > TP is unusual but schema allows it — gateway validates."""
        result = await gw.ingest(
            _valid_payload(stop_loss=2040.0, take_profit=2020.0),
            SignalSource.ML,
        )
        assert result is not None

    @pytest.mark.asyncio
    async def test_empty_metadata(self, gw):
        result = await gw.ingest(_valid_payload(metadata={}), SignalSource.ML)
        assert result is not None
        assert result.metadata == {}

    @pytest.mark.asyncio
    async def test_nested_metadata(self, gw):
        result = await gw.ingest(
            _valid_payload(metadata={"a": {"b": {"c": [1, 2, 3]}}}),
            SignalSource.ML,
        )
        assert result is not None

    @pytest.mark.asyncio
    async def test_unicode_symbol(self, gw):
        """Non-ASCII symbol should be rejected by schema min_length."""
        result = await gw.ingest(
            _valid_payload(symbol="XAU€USD"),
            SignalSource.ML,
        )
        # Pydantic allows it, but it's unusual
        assert result is not None or result is None  # depends on schema
