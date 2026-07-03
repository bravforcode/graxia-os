"""Tests for Entry Executor."""
import sys, random
sys.path.insert(0, r'C:\Users\menum\graxia os')
from datetime import datetime, timedelta
from graxia.packages.quant_os.regime.sweep_classifier import SweepSignal
from graxia.packages.quant_os.regime.entry_executor import EntryExecutor


def _make_bars(base=1.0850, count=30):
    bars = []
    price = base
    for i in range(count):
        t = datetime(2026, 6, 24, 8, 0) + timedelta(hours=i * 0.25)
        price += random.gauss(0, 0.0002)
        h = price + 0.0003; l = price - 0.0003
        bars.append({"time": t, "open": price, "high": h, "low": l, "close": price, "volume": 1000})
    return bars


def test_entry_reversal_buy():
    bars = _make_bars(1.0850)
    signal = SweepSignal(signal="REVERSAL", side="BUY", confidence=0.8,
                         quality_score=0.7, reclaim_score=0.8, reason_code="REVERSAL_BUY")
    ex = EntryExecutor(bars, balance=50000, spread=0.0001, avg_spread=0.0001, session="LONDON")
    result = ex.evaluate(signal, "EURUSD", 1.0850)
    assert result.should_enter, f"Should enter: {result.reason_code}"
    assert result.stop_price < result.entry_price, "SL below entry for BUY"
    assert result.take_profit > result.entry_price, "TP above entry for BUY"
    assert result.position_size > 0, "Non-zero size"
    print(f"  [OK] BUY reversal: entry={result.entry_price} SL={result.stop_price} TP={result.take_profit} size={result.position_size}")


def test_entry_reversal_sell():
    bars = _make_bars(1.0850)
    signal = SweepSignal(signal="REVERSAL", side="SELL", confidence=0.8,
                         quality_score=0.7, reclaim_score=0.8, reason_code="REVERSAL_SELL")
    ex = EntryExecutor(bars, balance=50000, spread=0.0001, avg_spread=0.0001, session="LONDON")
    result = ex.evaluate(signal, "EURUSD", 1.0850)
    assert result.should_enter
    assert result.stop_price > result.entry_price, "SL above entry for SELL"
    assert result.take_profit < result.entry_price, "TP below entry for SELL"
    print(f"  [OK] SELL reversal: entry={result.entry_price} SL={result.stop_price} TP={result.take_profit}")


def test_continuation_sell():
    bars = _make_bars(1.0850)
    signal = SweepSignal(signal="CONTINUATION", side="SELL", confidence=0.8,
                         quality_score=0.7, reclaim_score=0.8, reason_code="CONTINUATION_SELL")
    ex = EntryExecutor(bars, balance=50000, spread=0.0001, avg_spread=0.0001, session="LONDON")
    result = ex.evaluate(signal, "EURUSD", 1.0850)
    assert result.should_enter
    # Continuation uses 2R
    sl_dist = abs(result.stop_price - result.entry_price)
    tp_dist = abs(result.take_profit - result.entry_price)
    assert abs(tp_dist / sl_dist - 2.0) < 0.05, f"Expected 2R, got {tp_dist/sl_dist:.2f}R"
    print(f"  [OK] Continuation 2R: SL={sl_dist:.5f} TP={tp_dist:.5f} ratio={tp_dist/sl_dist:.1f}")


def test_low_confidence():
    bars = _make_bars(1.0850)
    signal = SweepSignal(signal="REVERSAL", side="BUY", confidence=0.3,
                         quality_score=0.2, reclaim_score=0.2, reason_code="LOW_CONF")
    ex = EntryExecutor(bars, balance=50000, spread=0.0001, avg_spread=0.0001, session="LONDON")
    result = ex.evaluate(signal, "EURUSD", 1.0850)
    assert not result.should_enter
    print(f"  [OK] Low confidence rejected: {result.reason_code}")


def test_spread_spike():
    bars = _make_bars(1.0850)
    signal = SweepSignal(signal="REVERSAL", side="BUY", confidence=0.8,
                         quality_score=0.7, reclaim_score=0.8, reason_code="REVERSAL_BUY")
    ex = EntryExecutor(bars, balance=50000, spread=0.001, avg_spread=0.0001, session="LONDON")
    result = ex.evaluate(signal, "EURUSD", 1.0850)
    assert not result.should_enter, f"Should reject: {result.reason_code}"
    print(f"  [OK] Spread spike rejected: {result.reason_code}")


def test_asian_session_filter():
    bars = _make_bars(1.0850)
    signal = SweepSignal(signal="REVERSAL", side="BUY", confidence=0.7,
                         quality_score=0.7, reclaim_score=0.8, reason_code="REVERSAL_BUY")
    ex = EntryExecutor(bars, balance=50000, spread=0.0001, avg_spread=0.0001, session="ASIAN")
    result = ex.evaluate(signal, "EURUSD", 1.0850)
    assert not result.should_enter, f"Should reject Asian: {result.reason_code}"
    print(f"  [OK] Asian session low conf rejected: {result.reason_code}")


def test_cooldown():
    bars = _make_bars(1.0850)
    signal = SweepSignal(signal="REVERSAL", side="BUY", confidence=0.8,
                         quality_score=0.7, reclaim_score=0.8, reason_code="REVERSAL_BUY")
    ex = EntryExecutor(bars, balance=50000, spread=0.0001, avg_spread=0.0001, session="LONDON")
    r1 = ex.evaluate(signal, "EURUSD", 1.0850)
    r2 = ex.evaluate(signal, "EURUSD", 1.0850)
    assert r1.should_enter, "First should enter"
    assert not r2.should_enter, "Second should be blocked by cooldown"
    print(f"  [OK] Cooldown: first={r1.should_enter} second={r2.should_enter} ({r2.reason_code})")


def test_position_size():
    random.seed(42)  # deterministic bars
    bars = _make_bars(1.0850)
    signal = SweepSignal(signal="REVERSAL", side="BUY", confidence=0.8,
                         quality_score=0.7, reclaim_score=0.8, reason_code="REVERSAL_BUY")
    ex = EntryExecutor(bars, balance=50000, spread=0.0001, avg_spread=0.0001, session="LONDON")
    result = ex.evaluate(signal, "EURUSD", 1.0850)
    risk = result.risk_amount
    # ponytail: with MIN_STOP_PRICE=0.001 and MAX_LEVERAGE=5, cap may reduce risk
    assert 0 < risk <= 50000 * 0.005, f"Risk ${risk:.2f} out of range (0, 250]"
    assert result.position_size > 0, "Position size must be positive"
    print(f"  [OK] Position size: risk=${risk:.2f} size={result.position_size:.4f}")


if __name__ == "__main__":
    random.seed(42)
    print("=== Entry Executor Tests ===\n")
    test_entry_reversal_buy()
    test_entry_reversal_sell()
    test_continuation_sell()
    test_low_confidence()
    test_spread_spike()
    test_asian_session_filter()
    test_cooldown()
    test_position_size()
    print("\n=== All tests passed ===")
