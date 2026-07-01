"""
Anti-leak regression tests for MultiTimeframeCursor.

These tests verify that strategies CANNOT see future lower-timeframe data.
If any test fails, the system has look-ahead leakage and results are invalid.
"""
from datetime import datetime, timedelta
from quant_os.backtest.mtf_cursor import MultiTimeframeCursor


def test_cursor_basic_slicing():
    """Cursor only returns data with timestamp <= as_of."""
    d1_data = {"close": [100, 101, 102, 103, 104], "high": [105]*5, "low": [95]*5}
    d1_ts = [
        datetime(2025, 1, 1),
        datetime(2025, 1, 2),
        datetime(2025, 1, 3),
        datetime(2025, 1, 4),
        datetime(2025, 1, 5),
    ]
    h1_data = {"close": [100.1, 100.2, 100.3, 101.1, 101.2, 102.1, 102.2, 103.1]}
    h1_ts = [
        datetime(2025, 1, 1, 1, 0),
        datetime(2025, 1, 1, 2, 0),
        datetime(2025, 1, 1, 3, 0),
        datetime(2025, 1, 2, 1, 0),
        datetime(2025, 1, 2, 2, 0),
        datetime(2025, 1, 3, 1, 0),
        datetime(2025, 1, 3, 2, 0),
        datetime(2025, 1, 4, 1, 0),
    ]

    cursor = MultiTimeframeCursor(d1_data, d1_ts, h1_data, h1_ts)

    # At D1 bar Jan 2, should only see H1 bars from Jan 1-2
    sliced = cursor.slice_as_of(datetime(2025, 1, 2, 23, 59))
    assert len(sliced["H1"]["close"]) == 5, f"Expected 5 H1 bars, got {len(sliced['H1']['close'])}"

    # At D1 bar Jan 1, should only see H1 bars from Jan 1
    sliced = cursor.slice_as_of(datetime(2025, 1, 1, 23, 59))
    assert len(sliced["H1"]["close"]) == 3, f"Expected 3 H1 bars, got {len(sliced['H1']['close'])}"

    # At D1 bar Jan 3, should see H1 bars from Jan 1-3
    sliced = cursor.slice_as_of(datetime(2025, 1, 3, 23, 59))
    assert len(sliced["H1"]["close"]) == 7, f"Expected 7 H1 bars, got {len(sliced['H1']['close'])}"

    # Before any data, should see nothing
    sliced = cursor.slice_as_of(datetime(2024, 12, 31))
    assert len(sliced["H1"]["close"]) == 0

    print("  PASS: test_cursor_basic_slicing")


def test_cursor_no_future_leak():
    """
    Core anti-leak test: adding future data MUST NOT change past slices.
    If this test fails, the system leaks.
    """
    # Base data: H1 bars up to Jan 3
    d1_data = {"close": [100, 101, 102], "high": [105]*3, "low": [95]*3}
    d1_ts = [datetime(2025, 1, 1), datetime(2025, 1, 2), datetime(2025, 1, 3)]
    h1_data_v1 = {"close": [100.1, 100.2, 101.1, 101.2, 102.1], "high": [105]*5, "low": [95]*5}
    h1_ts_v1 = [
        datetime(2025, 1, 1, 1, 0),
        datetime(2025, 1, 1, 2, 0),
        datetime(2025, 1, 2, 1, 0),
        datetime(2025, 1, 2, 2, 0),
        datetime(2025, 1, 3, 1, 0),
    ]

    cursor_v1 = MultiTimeframeCursor(d1_data, d1_ts, h1_data_v1, h1_ts_v1)

    # Slice at Jan 2 — baseline
    slice_v1 = cursor_v1.slice_as_of(datetime(2025, 1, 2, 23, 59))
    h1_count_v1 = len(slice_v1["H1"]["close"])
    h1_values_v1 = list(slice_v1["H1"]["close"])

    # Now add future H1 bars (Jan 4-10)
    h1_data_v2 = dict(h1_data_v1)
    h1_data_v2["close"] = h1_data_v1["close"] + [103.1, 103.2, 104.1, 104.2, 105.1]
    h1_ts_v2 = h1_ts_v1 + [
        datetime(2025, 1, 4, 1, 0),
        datetime(2025, 1, 4, 2, 0),
        datetime(2025, 1, 5, 1, 0),
        datetime(2025, 1, 5, 2, 0),
        datetime(2025, 1, 6, 1, 0),
    ]

    cursor_v2 = MultiTimeframeCursor(d1_data, d1_ts, h1_data_v2, h1_ts_v2)

    # Slice at Jan 2 — should be identical to v1
    slice_v2 = cursor_v2.slice_as_of(datetime(2025, 1, 2, 23, 59))
    h1_count_v2 = len(slice_v2["H1"]["close"])
    h1_values_v2 = list(slice_v2["H1"]["close"])

    assert h1_count_v1 == h1_count_v2, \
        f"LEAK DETECTED: count changed from {h1_count_v1} to {h1_count_v2} after adding future data"
    assert h1_values_v1 == h1_values_v2, \
        f"LEAK DETECTED: values changed after adding future data"

    print("  PASS: test_cursor_no_future_leak")


def test_cursor_mtf_strategy_invariant():
    """
    A strategy's signal at a given bar MUST NOT change when future lower-TF data is appended.
    This simulates the real backtest scenario.
    """
    from quant_os.gold_bot.strategies.liquidity_sweep import LiquiditySweepStrategy
    from quant_os.gold_bot.strategy_adapter import GoldStrategyAdapter

    # Create small test data
    import numpy as np
    np.random.seed(42)

    # D1 data: 10 bars
    closes = 2300 + np.cumsum(np.random.randn(10) * 5)
    d1_data = {
        "open": list(closes - 2),
        "high": list(closes + 5),
        "low": list(closes - 5),
        "close": list(closes),
        "volume": [1000] * 10,
    }
    d1_ts = [datetime(2025, 1, i+1, 7, 0) for i in range(10)]

    # H1 data v1: bars up to Jan 5
    h1_closes = 2300 + np.cumsum(np.random.randn(20) * 0.5)
    h1_data_v1 = {
        "open": list(h1_closes - 0.3),
        "high": list(h1_closes + 1),
        "low": list(h1_closes - 1),
        "close": list(h1_closes),
        "volume": [100] * 20,
    }
    h1_ts_v1 = [datetime(2025, 1, 1 + i // 24, i % 24, 0) for i in range(20)]

    # H1 data v2: same + 50 more bars into the future
    h1_closes_future = 2300 + np.cumsum(np.random.randn(70) * 0.5)
    h1_data_v2 = {
        "open": list(h1_closes_future - 0.3),
        "high": list(h1_closes_future + 1),
        "low": list(h1_closes_future - 1),
        "close": list(h1_closes_future),
        "volume": [100] * 70,
    }
    h1_ts_v2 = [datetime(2025, 1, 1 + i // 24, i % 24, 0) for i in range(70)]

    strategy = LiquiditySweepStrategy()

    # Run with v1 data
    adapter_v1 = GoldStrategyAdapter(strategy)
    cursor_v1 = MultiTimeframeCursor(d1_data, d1_ts, h1_data_v1, h1_ts_v1)

    signals_v1 = []
    for i in range(5, 10):  # Bars 5-9
        sliced = cursor_v1.slice_as_of(d1_ts[i])
        adapter_v1._set_mtf_cursor(sliced)
        bar_data = {k: v[:i+1] for k, v in d1_data.items()}
        sig = adapter_v1.generate_signal("XAUUSD", bar_data, current_time=d1_ts[i])
        signals_v1.append(sig.signal_type.value if sig else None)

    # Run with v2 data (more future bars)
    adapter_v2 = GoldStrategyAdapter(strategy)
    cursor_v2 = MultiTimeframeCursor(d1_data, d1_ts, h1_data_v2, h1_ts_v2)

    signals_v2 = []
    for i in range(5, 10):
        sliced = cursor_v2.slice_as_of(d1_ts[i])
        adapter_v2._set_mtf_cursor(sliced)
        bar_data = {k: v[:i+1] for k, v in d1_data.items()}
        sig = adapter_v2.generate_signal("XAUUSD", bar_data, current_time=d1_ts[i])
        signals_v2.append(sig.signal_type.value if sig else None)

    assert signals_v1 == signals_v2, \
        f"STRATEGY LEAK: signals changed from {signals_v1} to {signals_v2}"

    print("  PASS: test_cursor_mtf_strategy_invariant")


def test_cursor_current_bar_incomplete():
    """The current forming bar should NOT be visible to strategies."""
    d1_data = {"close": [100, 101, 102], "high": [105]*3, "low": [95]*3}
    d1_ts = [datetime(2025, 1, 1), datetime(2025, 1, 2), datetime(2025, 1, 3)]
    h1_data = {"close": [100.1, 100.2, 101.1, 101.2, 102.1, 102.2], "high": [105]*6, "low": [95]*6}
    h1_ts = [
        datetime(2025, 1, 1, 1, 0),
        datetime(2025, 1, 1, 2, 0),
        datetime(2025, 1, 2, 1, 0),
        datetime(2025, 1, 2, 2, 0),
        datetime(2025, 1, 3, 1, 0),
        datetime(2025, 1, 3, 2, 0),  # This bar is AT the D1 close time
    ]

    cursor = MultiTimeframeCursor(d1_data, d1_ts, h1_data, h1_ts)

    # Slice at exact D1 bar close time (Jan 3 07:00)
    # H1 bar at Jan 3 07:00 doesn't exist, so no incomplete bar issue
    sliced = cursor.slice_as_of(datetime(2025, 1, 3, 7, 0))
    assert len(sliced["H1"]["close"]) == 6

    # Exclusive mode: should exclude bars at exactly as_of
    sliced_exc = cursor.slice_as_of_exclusive(datetime(2025, 1, 3, 2, 0))
    assert len(sliced_exc["H1"]["close"]) == 5, \
        f"Exclusive should exclude bar at as_of: got {len(sliced_exc['H1']['close'])}"

    print("  PASS: test_cursor_current_bar_incomplete")


if __name__ == "__main__":
    print("=" * 60)
    print("ANTI-LEAK TESTS")
    print("=" * 60)
    test_cursor_basic_slicing()
    test_cursor_no_future_leak()
    test_cursor_mtf_strategy_invariant()
    test_cursor_current_bar_incomplete()
    print("\nAll anti-leak tests passed.")
