"""Tests for differential comparator."""
from graxia.packages.quant_os.oracle.differential_comparator import DifferentialComparator


def test_comparator_identical():
    comp = DifferentialComparator()
    signals = [
        {"direction": "BUY", "entry_price": 2350.50, "stop_loss": 2348.50, "take_profit": 2354.50, "timestamp_utc": "2026-06-22T10:00:00"},
    ]
    result = comp.compare_signals(signals, signals)
    assert result.match
    assert result.signal_count_a == 1


def test_comparator_direction_mismatch():
    comp = DifferentialComparator()
    a = [{"direction": "BUY", "entry_price": 100, "stop_loss": 99, "take_profit": 102, "timestamp_utc": "t1"}]
    b = [{"direction": "SELL", "entry_price": 100, "stop_loss": 99, "take_profit": 102, "timestamp_utc": "t1"}]
    result = comp.compare_signals(a, b)
    assert not result.match
    assert result.direction_mismatches == 1


def test_comparator_count_mismatch():
    comp = DifferentialComparator()
    a = [{"direction": "BUY", "entry_price": 100, "stop_loss": 99, "take_profit": 102, "timestamp_utc": "t1"}]
    b = []
    result = comp.compare_signals(a, b)
    assert not result.match
    assert result.signal_count_a == 1
    assert result.signal_count_b == 0


def test_comparator_tolerance():
    comp = DifferentialComparator(tolerance_pct=0.5)
    a = [{"direction": "BUY", "entry_price": 100.0, "stop_loss": 99.0, "take_profit": 102.0, "timestamp_utc": "t1"}]
    b = [{"direction": "BUY", "entry_price": 100.1, "stop_loss": 99.1, "take_profit": 102.1, "timestamp_utc": "t1"}]
    result = comp.compare_signals(a, b)
    assert result.match  # within tolerance
