"""Tests for Sweep Classifier."""
import sys, random
sys.path.insert(0, r'C:\Users\menum\graxia os')
from datetime import datetime, timedelta
from graxia.packages.quant_os.regime.liquidity_map import LiquidityLevel
from graxia.packages.quant_os.regime.sweep_classifier import SweepClassifier


def _make_bars(base=1.0850, count=30, noise=0.0002):
    bars = []
    price = base
    for i in range(count):
        t = datetime(2026, 6, 24, 8, 0) + timedelta(hours=i * 0.25)
        price += random.gauss(0, noise)
        high = price + abs(random.gauss(0, noise * 0.5))
        low = price - abs(random.gauss(0, noise * 0.5))
        bars.append({"time": t, "open": price, "high": high, "low": low, "close": price, "volume": 1000})
    return bars


def _make_reversal_bars(sweep_up=True, base=1.0850):
    """Sweep level + reclaim. sweep_up: sweep above level (resistance)."""
    bars = []
    for i in range(30):
        t = datetime(2026, 6, 24, 8, 0) + timedelta(hours=i * 0.25)
        if sweep_up:
            # Sweep above resistance, close back below
            if i < 20:
                p = base - 0.0002; h = p + 0.0003; l = p - 0.0003
            elif i == 20:
                p = base - 0.0002; h = base + 0.003; l = base - 0.0005
            else:
                p = base - 0.0003; h = p + 0.0003; l = p - 0.0003
        else:
            # Sweep below support, close back above
            if i < 20:
                p = base + 0.0002; h = p + 0.0003; l = p - 0.0003
            elif i == 20:
                p = base + 0.0002; h = base + 0.0003; l = base - 0.003
            else:
                p = base + 0.0003; h = p + 0.0003; l = p - 0.0003
        bars.append({"time": t, "open": p, "high": h, "low": l, "close": p, "volume": 1000})
    return bars


def _make_continuation_bars(trend_up=True, base=1.0850, level=1.0880):
    """Break above level + no reclaim."""
    bars = []
    for i in range(30):
        t = datetime(2026, 6, 24, 8, 0) + timedelta(hours=i * 0.25)
        if i < 20:
            drift = 0.0001 if trend_up else -0.0001
            p = base + drift * i; h = p + 0.0005; l = p - 0.0005
        elif i == 20:
            p = level + 0.002; h = p + 0.002; l = level + 0.0005  # break above level
        else:
            drift = 0.0002 if trend_up else -0.0002
            p = bars[-1]["close"] + drift; h = p + 0.0005; l = p - 0.0005
        bars.append({"time": t, "open": p, "high": h, "low": l, "close": p, "volume": 1500})
    return bars


def test_reversal_buy():
    bars = _make_reversal_bars(sweep_up=False, base=1.0850)
    levels = [LiquidityLevel(level_type="SWING_L", price=1.0850, strength_score=0.8, reason_code="SWING_L@20")]
    sc = SweepClassifier(bars, levels, regime="RANGE", spread_state="NORMAL")
    signals = sc.classify()
    rev = [s for s in signals if s.signal == "REVERSAL" and s.side == "BUY"]
    assert len(rev) > 0, "No BUY reversal"
    print(f"  [OK] BUY reversal conf={[s.confidence for s in rev]}")


def test_reversal_sell():
    bars = _make_reversal_bars(sweep_up=True, base=1.0850)
    levels = [LiquidityLevel(level_type="SWING_H", price=1.0850, strength_score=0.8, reason_code="SWING_H@20")]
    sc = SweepClassifier(bars, levels, regime="RANGE", spread_state="NORMAL")
    signals = sc.classify()
    rev = [s for s in signals if s.signal == "REVERSAL" and s.side == "SELL"]
    assert len(rev) > 0, "No SELL reversal"
    print(f"  [OK] SELL reversal conf={[s.confidence for s in rev]}")


def test_continuation():
    bars = _make_continuation_bars(trend_up=True, base=1.0850, level=1.0880)
    levels = [LiquidityLevel(level_type="SWING_H", price=1.0880, strength_score=0.8, reason_code="SWING_H@20")]
    sc = SweepClassifier(bars, levels, regime="TREND_UP", spread_state="NORMAL")
    signals = sc.classify()
    con = [s for s in signals if s.signal == "CONTINUATION"]
    print(f"  [INFO] Continuation: {[(s.side, s.confidence) for s in con]}")


def test_no_trade_spread_spike():
    bars = _make_reversal_bars(sweep_up=False, base=1.0850)
    levels = [LiquidityLevel(level_type="SWING_L", price=1.0850, strength_score=0.8, reason_code="SWING_L@20")]
    sc = SweepClassifier(bars, levels, regime="RANGE", spread_state="SPIKE")
    assert len(sc.classify()) == 0, "Should be NO_TRADE during spike"
    print("  [OK] No trade during spread spike")


def test_no_trade_unclear():
    bars = _make_reversal_bars(sweep_up=False, base=1.0850)
    levels = [LiquidityLevel(level_type="SWING_L", price=1.0850, strength_score=0.8, reason_code="SWING_L@20")]
    sc = SweepClassifier(bars, levels, regime="UNCLEAR", spread_state="NORMAL")
    assert len(sc.classify()) == 0, "Should be NO_TRADE in UNCLEAR"
    print("  [OK] No trade in UNCLEAR regime")


def test_insufficient_bars():
    bars = _make_bars(base=1.0850, count=5)
    sc = SweepClassifier(bars, [], regime="RANGE", spread_state="NORMAL")
    assert len(sc.classify()) == 0
    print("  [OK] Insufficient bars")


def test_no_sweep():
    bars = _make_bars(base=1.0850, count=30)
    levels = [LiquidityLevel(level_type="SWING_H", price=1.10, strength_score=0.8, reason_code="SWING_H@5")]
    sc = SweepClassifier(bars, levels, regime="RANGE", spread_state="NORMAL")
    assert len(sc.classify()) == 0
    print("  [OK] No sweep -> empty")


def test_output():
    bars = _make_reversal_bars(sweep_up=False, base=1.0850)
    levels = [LiquidityLevel(level_type="SWING_L", price=1.0850, strength_score=0.8, reason_code="SWING_L@20")]
    sc = SweepClassifier(bars, levels, regime="RANGE", spread_state="NORMAL")
    for s in sc.classify():
        assert all(hasattr(s, a) for a in ["signal","side","confidence","quality_score","reclaim_score","invalidation_price"])
    print("  [OK] Output format")


if __name__ == "__main__":
    random.seed(42)
    print("=== Sweep Classifier Tests ===\n")
    test_reversal_buy()
    test_reversal_sell()
    test_continuation()
    test_no_trade_spread_spike()
    test_no_trade_unclear()
    test_insufficient_bars()
    test_no_sweep()
    test_output()
    print("\n=== All tests passed ===")
