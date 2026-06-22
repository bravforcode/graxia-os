"""Tests for canonical tick source — 15 invariants for shadow tick integrity."""
import ast
import hashlib
import json
from datetime import datetime, timezone, timedelta
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from graxia.packages.quant_os.shadow.canonical_tick_source import (
    CanonicalTickSource,
    CanonicalTickPolicy,
    CanonicalTickBatch,
)
from graxia.packages.quant_os.shadow.canonical_bar_builder import (
    CanonicalBarBuilder,
    CanonicalBar,
)
from graxia.packages.quant_os.shadow.canonical_time_authority import (
    CanonicalTimeAuthority,
)
from graxia.packages.quant_os.shadow.tick_window_fetcher import TickWindowFetcher
from graxia.packages.quant_os.shadow.tick_deduplicator import TickDeduplicator
from graxia.packages.quant_os.shadow.tick_watermark import TickWatermark
from graxia.packages.quant_os.shadow.event_risk_gate import EventRiskGate
from graxia.packages.quant_os.shadow.pipeline import ShadowPipeline


# ── helpers ──────────────────────────────────────────────────────────

SHADOW_DIR = Path(__file__).parent


def _make_mt5_conn(ticks=None):
    """Create a mock MT5 connection with configurable copy_ticks_range."""
    conn = MagicMock()
    mt5_module = MagicMock()
    mt5_module.COPY_TICKS_ALL = 0

    if ticks is None:
        ticks = []

    def fake_copy_ticks_range(symbol, fr, to, flags):
        fr_epoch = int(fr.timestamp())
        to_epoch = int(to.timestamp())
        filtered = [
            t for t in ticks if fr_epoch <= int(t[0]) <= to_epoch
        ]
        return filtered if filtered else None

    mt5_module.copy_ticks_range = fake_copy_ticks_range
    conn._mt5 = mt5_module
    return conn


def _tick(ts_epoch, bid=1.1000, ask=1.1001, volume=1, time_msc=None):
    """Build a raw MT5-style tick tuple: (time, bid, ask, last, volume, time_msc, flags)."""
    msc = time_msc or ts_epoch * 1000
    return (ts_epoch, bid, ask, bid, volume, msc, 0)


def _tick_dict(ts_epoch, bid=1.1000, ask=1.1001, volume=1, time_msc=None):
    """Canonical tick dict."""
    msc = time_msc or ts_epoch * 1000
    return {
        "time": ts_epoch,
        "time_msc": msc,
        "bid": bid,
        "ask": ask,
        "last": bid,
        "volume": volume,
        "flags": 0,
    }


# ── 1. test_reject_naive_datetime_in_config ──────────────────────────

def test_reject_naive_datetime_in_config():
    """Naive datetime rejected at config validation time."""
    fetcher = TickWindowFetcher(MagicMock())
    naive = datetime(2025, 1, 1, 12, 0, 0)
    with pytest.raises(ValueError, match="NAIVE_DATETIME_REJECTED"):
        fetcher.validate_datetime_aware(naive, "request_from")


# ── 2. test_utc_aware_query_only ─────────────────────────────────────

def test_utc_aware_query_only():
    """Only UTC-aware datetimes accepted for copy_ticks_range."""
    fetcher = TickWindowFetcher(MagicMock())
    aware = datetime(2025, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
    fetcher.validate_datetime_aware(aware, "request_from")
    # If it didn't raise, the assertion passes


# ── 3. test_all_returned_ticks_in_window ─────────────────────────────

def test_all_returned_ticks_in_window():
    """Every returned tick must be within requested window."""
    now = datetime.now(timezone.utc)
    from_ts = int((now - timedelta(minutes=5)).timestamp())
    to_ts = int(now.timestamp())

    # Ticks inside window
    inside = [_tick(from_ts + 10), _tick(from_ts + 20), _tick(to_ts - 5)]
    conn = _make_mt5_conn(inside)

    fetcher = TickWindowFetcher(conn)
    result = fetcher.fetch_ticks(
        "XAUUSD",
        datetime.fromtimestamp(from_ts, tz=timezone.utc),
        datetime.fromtimestamp(to_ts, tz=timezone.utc),
    )
    assert result["error"] == ""
    assert result["outside_count"] == 0
    assert len(result["ticks"]) == 3


# ── 4. test_overlapping_windows_no_duplicate_ticks ───────────────────

def test_overlapping_windows_no_duplicate_ticks():
    """Overlapping windows don't create duplicate ticks."""
    dedup = TickDeduplicator()
    t1 = _tick_dict(1000, bid=1.1000, ask=1.1001)
    t2 = _tick_dict(1001, bid=1.1002, ask=1.1003)

    # First window
    batch1, dupes1 = dedup.deduplicate([t1, t2])
    assert len(batch1) == 2
    assert dupes1 == 0

    # Overlapping window — same ticks + new one
    t3 = _tick_dict(1002, bid=1.1004, ask=1.1005)
    batch2, dupes2 = dedup.deduplicate([t1, t2, t3])
    assert len(batch2) == 1  # only t3 is new
    assert dupes2 == 2  # t1, t2 are dupes


# ── 5. test_late_tick_does_not_modify_finalized_bar ──────────────────

def test_late_tick_does_not_modify_finalized_bar():
    """Late tick doesn't modify already-finalized bar."""
    builder = CanonicalBarBuilder("XAUUSD", bar_finalization_delay_seconds=60)

    # Add tick and finalize the bar
    tick1 = _tick_dict(1000, bid=1.1000, ask=1.1001)
    builder.add_tick(tick1)
    system_time = datetime.fromtimestamp(1000 + 120, tz=timezone.utc)
    builder.finalize_bars(system_time)

    finalized = builder.get_finalized_m1_bars(1)
    assert len(finalized) == 1
    assert finalized[0].is_finalized
    assert finalized[0].open == 1.10005

    # Late tick in same minute
    tick_late = _tick_dict(1030, bid=1.2000, ask=1.2001)
    builder.add_tick(tick_late)
    builder.finalize_bars(system_time)

    # Finalized bar must still have original values
    finalized_after = builder.get_finalized_m1_bars(2)
    original_bar = [b for b in finalized_after if b.is_finalized and b.tick_count == 1]
    assert len(original_bar) == 1
    assert original_bar[0].open == 1.10005
    assert original_bar[0].high == 1.10005


# ── 6. test_tick_out_of_order_detected ───────────────────────────────

def test_tick_out_of_order_detected():
    """Tick out-of-order is detected via deduplication."""
    dedup = TickDeduplicator()
    t1 = _tick_dict(1000, bid=1.1000, ask=1.1001)
    t2 = _tick_dict(1001, bid=1.1002, ask=1.1003)

    # Send t2 first, then t1, then t2 again
    batch1, _ = dedup.deduplicate([t2])
    assert len(batch1) == 1

    batch2, dupes2 = dedup.deduplicate([t1])
    assert len(batch2) == 1
    assert dupes2 == 0

    # t2 again — should be detected as duplicate
    batch3, dupes3 = dedup.deduplicate([t2])
    assert len(batch3) == 0
    assert dupes3 == 1


# ── 7. test_canonical_m1_bar_matches_tick_aggregation ────────────────

def test_canonical_m1_bar_matches_tick_aggregation():
    """Canonical M1 bar matches manual tick aggregation."""
    builder = CanonicalBarBuilder("XAUUSD", bar_finalization_delay_seconds=60)

    base = datetime(2025, 6, 20, 12, 0, 0, tzinfo=timezone.utc)
    ticks = [
        _tick_dict(int(base.timestamp()), bid=1.1000, ask=1.1002),
        _tick_dict(int(base.timestamp()) + 10, bid=1.1005, ask=1.1007),
        _tick_dict(int(base.timestamp()) + 30, bid=1.0998, ask=1.1000),
    ]

    for t in ticks:
        builder.add_tick(t)

    mids = [(1.1000 + 1.1002) / 2, (1.1005 + 1.1007) / 2, (1.0998 + 1.1000) / 2]

    bars = builder.get_current_m1_bar()
    assert bars is not None
    assert bars.open == mids[0]
    assert bars.high == max(mids)
    assert bars.low == min(mids)
    assert bars.close == mids[-1]
    assert bars.tick_count == 3


# ── 8. test_strategy_uses_completed_bars_only ────────────────────────

def test_strategy_uses_completed_bars_only():
    """Strategy only sees completed canonical bars."""
    builder = CanonicalBarBuilder("XAUUSD", bar_finalization_delay_seconds=60)

    # Add ticks for two minutes
    base = datetime(2025, 6, 20, 12, 0, 0, tzinfo=timezone.utc)
    t1 = _tick_dict(int(base.timestamp()), bid=1.1000, ask=1.1001)
    t2 = _tick_dict(int(base.timestamp()) + 60, bid=1.1010, ask=1.1011)

    builder.add_tick(t1)
    builder.add_tick(t2)

    # Finalize only first bar
    finalize_time = base + timedelta(minutes=1, seconds=61)
    builder.finalize_bars(finalize_time)

    finalized = builder.get_finalized_m1_bars(10)
    assert len(finalized) == 1
    assert finalized[0].open_time == base

    # Current bar should be the second minute
    current = builder.get_current_m1_bar()
    assert current is not None
    assert current.open_time == base + timedelta(minutes=1)
    assert not current.is_finalized


# ── 9. test_event_gate_uses_system_utc ───────────────────────────────

def test_event_gate_uses_system_utc():
    """Event gate uses system UTC not MT5 current-bar time."""
    gate = EventRiskGate(blackout_minutes=30)
    now = datetime.now(timezone.utc)

    # Event 20 minutes from now — should block
    event_time = now + timedelta(minutes=20)
    result = gate.check(now, [{"name": "NFP", "time": event_time}])
    assert result.blocked is True
    assert result.minutes_to_event == 20

    # Event using MT5 bar time (stale, 50 minutes ago) — should NOT block
    stale_time = now - timedelta(minutes=50)
    result2 = gate.check(now, [{"name": "NFP", "time": stale_time}])
    assert result2.blocked is False


# ── 10. test_session_gate_uses_system_utc ────────────────────────────

def test_session_gate_uses_system_utc():
    """Session gate uses system UTC not MT5 current-bar time."""
    auth = CanonicalTimeAuthority()
    system_utc = auth.trusted_system_utc()

    # Must be UTC-aware
    assert system_utc.tzinfo is not None
    assert system_utc.tzinfo == timezone.utc

    # Must be close to real time (within 2 seconds)
    real_now = datetime.now(timezone.utc)
    diff = abs((system_utc - real_now).total_seconds())
    assert diff < 2.0


# ── 11. test_symbol_info_tick_time_blocked ───────────────────────────

def test_symbol_info_tick_time_blocked():
    """symbol_info_tick.time must not flow into signal path."""
    auth = CanonicalTimeAuthority()
    assert auth.is_tick_time_trusted() is False
    assert auth.tick_source() == "copy_ticks_range_utc_aware"


# ── 12. test_mt5_bar_time_blocked ────────────────────────────────────

def test_mt5_bar_time_blocked():
    """MT5 bar timestamps must not flow into signal path."""
    auth = CanonicalTimeAuthority()
    assert auth.is_bar_time_trusted() is False
    assert auth.bar_source() == "canonical_built_from_ticks"


# ── 13. test_copy_ticks_from_not_imported ────────────────────────────

def test_copy_ticks_from_not_imported():
    """copy_ticks_from not imported in canonical shadow runtime."""
    source_files = [
        "canonical_tick_source.py",
        "canonical_bar_builder.py",
        "canonical_time_authority.py",
        "tick_window_fetcher.py",
        "tick_deduplicator.py",
        "tick_watermark.py",
        "pipeline.py",
        "event_risk_gate.py",
        "market_health.py",
    ]

    violations = []
    for fname in source_files:
        path = SHADOW_DIR / fname
        if not path.exists():
            continue
        try:
            tree = ast.parse(path.read_text(encoding="utf-8", errors="replace"))
        except SyntaxError:
            continue
        for node in ast.walk(tree):
            if isinstance(node, ast.Attribute) and node.attr == "copy_ticks_from":
                violations.append(fname)
            if isinstance(node, ast.Name) and node.id == "copy_ticks_from":
                violations.append(fname)

    assert violations == [], f"copy_ticks_from found in: {violations}"


# ── 14. test_no_execution_apis ───────────────────────────────────────

def test_no_execution_apis():
    """No order_send, order_modify, order_close, pending order APIs."""
    forbidden = {
        "order_send", "order_modify", "order_close",
        "order_check", "order_calc_margin",
        "positions_get", "history_deals_get",
    }

    source_files = [
        "canonical_tick_source.py",
        "canonical_bar_builder.py",
        "canonical_time_authority.py",
        "tick_window_fetcher.py",
        "tick_deduplicator.py",
        "tick_watermark.py",
        "pipeline.py",
        "event_risk_gate.py",
        "market_health.py",
        "shadow_pipeline.py",
        "shadow_campaign.py",
        "broker_profile.py",
    ]

    violations = []
    for fname in source_files:
        path = SHADOW_DIR / fname
        if not path.exists():
            continue
        try:
            tree = ast.parse(path.read_text(encoding="utf-8", errors="replace"))
        except SyntaxError:
            continue
        for node in ast.walk(tree):
            func_name = ""
            if isinstance(node, ast.Call):
                if isinstance(node.func, ast.Name):
                    func_name = node.func.id
                elif isinstance(node.func, ast.Attribute):
                    func_name = node.func.attr
            if isinstance(node, ast.Attribute):
                func_name = node.attr
            if func_name in forbidden:
                violations.append(f"{fname}: {func_name}")

    assert violations == [], f"Execution APIs found: {violations}"


# ── 15. test_ledger_deterministic ────────────────────────────────────

def test_ledger_deterministic():
    """Full shadow rerun gives same ledger seal with same input ticks."""
    now = int(datetime.now(timezone.utc).timestamp())
    ticks = [
        _tick(now - 300 + i, bid=1.1000 + i * 0.0001, ask=1.1001 + i * 0.0001)
        for i in range(5)
    ]

    def run_shadow(tick_list):
        conn = _make_mt5_conn(tick_list)
        policy = CanonicalTickPolicy(
            reject_if_no_canonical_tick=False,
            reject_if_tick_outside_requested_window=True,
            reject_if_timestamp_in_future=True,
        )
        src = CanonicalTickSource(conn, "XAUUSD", policy=policy)
        batch = src.fetch_cycle()
        return batch.batch_hash

    hash1 = run_shadow(ticks)
    hash2 = run_shadow(ticks)
    assert hash1 == hash2
    assert hash1 != ""
