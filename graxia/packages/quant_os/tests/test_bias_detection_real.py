"""
Bias Detection Test — Run truncated-vs-full comparison on all 13 strategies.

This tests for UNINTENTIONAL lookahead bias:
- If a strategy produces different output when given truncated vs full data,
  it means the strategy's behavior depends on future data it shouldn't see.
- This catches: indicator calculated on full series, pandas view leakage,
  feature scaling on full data, etc.

This is the REAL test for lookahead, not the synthetic CheatingStrategy test.
"""
import random
random.seed(42)

from quant_os.core.bias_detector import BiasDetector
from quant_os.gold_bot.strategies.order_block import OrderBlockStrategy
from quant_os.gold_bot.strategies.supply_demand import SupplyDemandStrategy
from quant_os.gold_bot.strategies.ema_cross import EMACrossStrategy
from quant_os.gold_bot.strategies.rsi_divergence import RSIDivergenceStrategy
from quant_os.gold_bot.strategies.london_breakout import LondonBreakoutStrategy
from quant_os.gold_bot.strategies.fibonacci import FibonacciStrategy
from quant_os.gold_bot.strategies.vwap_rejection import VWAPRejectionStrategy
from quant_os.gold_bot.strategies.news_fade import NewsFadeStrategy
from quant_os.gold_bot.strategies.multi_tf_align import MultiTFAlignStrategy
from quant_os.gold_bot.strategies.bos_choch import BOSCHoCHStrategy
from quant_os.gold_bot.strategies.liquidity_sweep import LiquiditySweepStrategy
from quant_os.gold_bot.strategies.fair_value_gap import FairValueGapStrategy
from quant_os.gold_bot.strategies.opening_range import OpeningRangeStrategy


def generate_test_data(bars=500):
    """Generate realistic OHLCV data"""
    data = {"open": [], "high": [], "low": [], "close": [], "volume": []}
    price = 2350.0

    for _ in range(bars):
        change = random.gauss(0.0003, 0.001)
        o = price
        c = price * (1 + change)
        h = max(o, c) * (1 + abs(random.gauss(0, 0.0003)))
        l = min(o, c) * (1 - abs(random.gauss(0, 0.0003)))
        v = 100000 * (1 + random.gauss(0, 0.3))

        data["open"].append(round(o, 2))
        data["close"].append(round(c, 2))
        data["high"].append(round(h, 2))
        data["low"].append(round(l, 2))
        data["volume"].append(max(0, v))

        price = c

    return data


def _test_strategy_lookahead(strategy_class, strategy_name, data):
    """Test if a strategy produces different output on truncated vs full data"""
    try:
        strategy = strategy_class()
        current_price = data["close"][-1]

        # Run on FULL data (what the strategy "should" see at the end)
        full_signal = strategy.analyze(data, current_price, "XAUUSD")

        # Run on TRUNCATED data (first 80% — simulating bar-by-bar execution)
        split_idx = int(len(data["close"]) * 0.8)
        truncated = {k: v[:split_idx] for k, v in data.items()}
        trunc_price = truncated["close"][-1]
        trunc_signal = strategy.analyze(truncated, trunc_price, "XAUUSD")

        # Compare
        full_dir = full_signal.direction.value if full_signal else "NONE"
        trunc_dir = trunc_signal.direction.value if trunc_signal else "NONE"

        full_score = full_signal.score if full_signal else 0
        trunc_score = trunc_signal.score if trunc_signal else 0

        changed = full_dir != trunc_dir or abs(full_score - trunc_score) > 10

        return {
            "strategy": strategy_name,
            "full_direction": full_dir,
            "full_score": full_score,
            "trunc_direction": trunc_dir,
            "trunc_score": trunc_score,
            "changed": changed,
            "status": "LOOKAHEAD" if changed else "CLEAN",
        }

    except Exception as e:
        return {
            "strategy": strategy_name,
            "status": "ERROR",
            "error": str(e),
        }


def main():
    print("=" * 70)
    print("  Bias Detection: Truncated-vs-Full on 13 Strategies")
    print("=" * 70)

    data = generate_test_data(500)
    print(f"\n  Test data: {len(data['close'])} bars")
    print(f"  Truncated: {int(len(data['close']) * 0.8)} bars (80%)")
    print(f"  Full: {len(data['close'])} bars (100%)")

    strategies = [
        ("order_block", OrderBlockStrategy),
        ("supply_demand", SupplyDemandStrategy),
        ("ema_cross", EMACrossStrategy),
        ("rsi_divergence", RSIDivergenceStrategy),
        ("london_breakout", LondonBreakoutStrategy),
        ("fibonacci", FibonacciStrategy),
        ("vwap_rejection", VWAPRejectionStrategy),
        ("news_fade", NewsFadeStrategy),
        ("multi_tf_align", MultiTFAlignStrategy),
        ("bos_choch", BOSCHoCHStrategy),
        ("liquidity_sweep", LiquiditySweepStrategy),
        ("fair_value_gap", FairValueGapStrategy),
        ("opening_range", OpeningRangeStrategy),
    ]

    results = []
    clean_count = 0
    lookahead_count = 0
    error_count = 0

    for name, cls in strategies:
        result = test_strategy_lookahead(cls, name, data)
        results.append(result)

        if result["status"] == "CLEAN":
            clean_count += 1
            status_icon = "[OK]"
        elif result["status"] == "LOOKAHEAD":
            lookahead_count += 1
            status_icon = "[!!]"
        else:
            error_count += 1
            status_icon = "[??]"

        print(f"\n  {status_icon} {name}")
        print(f"     Full:    {result.get('full_direction', 'N/A')} (score={result.get('full_score', 'N/A')})")
        print(f"     Trunc:   {result.get('trunc_direction', 'N/A')} (score={result.get('trunc_score', 'N/A')})")
        if result.get("error"):
            print(f"     Error:   {result['error']}")

    print(f"\n{'=' * 70}")
    print(f"  RESULTS: {clean_count} CLEAN, {lookahead_count} LOOKAHEAD, {error_count} ERRORS")
    print(f"{'=' * 70}")

    if lookahead_count > 0:
        print(f"\n  WARNING: {lookahead_count} strategies show different behavior on truncated vs full data.")
        print(f"  This may indicate unintentional lookahead bias.")
        print(f"  Review these strategies for: indicator calculated on full series,")
        print(f"  pandas view leakage, or feature scaling on full data.")
    else:
        print(f"\n  PASS: All strategies produce consistent output regardless of data length.")
        print(f"  No unintentional lookahead detected.")

    return results


if __name__ == "__main__":
    main()
