import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from repo_intelligence.differential_comparator import (
    compare_signal_ledgers,
    compare_metrics,
)


def test_identical_ledgers_match():
    trades = [
        {"side": "long", "timestamp_utc": "2025-01-01T00:00:00", "exit_reason": "tp", "pnl_net": 10.0},
        {"side": "short", "timestamp_utc": "2025-01-02T00:00:00", "exit_reason": "sl", "pnl_net": -5.0},
    ]
    result = compare_signal_ledgers(trades, trades)
    assert result.match
    assert len(result.mismatches) == 0
    assert len(result.warnings) == 0


def test_side_mismatch_detected():
    a = [{"side": "long", "timestamp_utc": "2025-01-01T00:00:00", "exit_reason": "tp", "pnl_net": 10.0}]
    b = [{"side": "short", "timestamp_utc": "2025-01-01T00:00:00", "exit_reason": "tp", "pnl_net": 10.0}]
    result = compare_signal_ledgers(a, b)
    assert not result.match
    assert any(m["field"] == "trade_0.side" for m in result.mismatches)


def test_trade_count_mismatch_detected():
    a = [{"side": "long", "timestamp_utc": "2025-01-01T00:00:00", "exit_reason": "tp", "pnl_net": 10.0}]
    b = []
    result = compare_signal_ledgers(a, b)
    assert not result.match
    assert any(m["field"] == "trade_count" for m in result.mismatches)


def test_pnl_difference_is_warning_not_error():
    a = [{"side": "long", "timestamp_utc": "2025-01-01T00:00:00", "exit_reason": "tp", "pnl_net": 10.0}]
    b = [{"side": "long", "timestamp_utc": "2025-01-01T00:00:00", "exit_reason": "tp", "pnl_net": 12.0}]
    result = compare_signal_ledgers(a, b)
    assert result.match
    assert any(w["field"] == "trade_0.pnl" for w in result.warnings)


def test_exit_reason_mismatch_detected():
    a = [{"side": "long", "timestamp_utc": "2025-01-01T00:00:00", "exit_reason": "tp", "pnl_net": 10.0}]
    b = [{"side": "long", "timestamp_utc": "2025-01-01T00:00:00", "exit_reason": "sl", "pnl_net": 10.0}]
    result = compare_signal_ledgers(a, b)
    assert not result.match
    assert any(m["field"] == "trade_0.exit_reason" for m in result.mismatches)


def test_metrics_comparison():
    c = {"total_trades": 100, "win_rate": 0.6, "profit_factor": 1.5, "total_pnl": 500.0}
    o = {"total_trades": 100, "win_rate": 0.6, "profit_factor": 1.5, "total_pnl": 520.0}
    result = compare_metrics(c, o)
    assert result.match
    assert any(w["field"] == "total_pnl" for w in result.warnings)

    o2 = {"total_trades": 95, "win_rate": 0.6, "profit_factor": 1.5, "total_pnl": 500.0}
    result2 = compare_metrics(c, o2)
    assert not result2.match
    assert any(m["field"] == "total_trades" for m in result2.mismatches)
