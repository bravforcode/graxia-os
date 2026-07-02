"""
Diagnostic: Run MRB and MLB through ACTUAL generate_signal() method.
Logs partial condition hits and how close each sub-condition is to threshold.
"""

from decimal import Decimal

from quant_os.core.enums import RegimeType, SignalType
from quant_os.strategies.mlb import MLBreakout
from quant_os.strategies.mrb import MeanReversionBollinger


def generate_trending_data(n=500, start=1.0850, drift=0.0003):
    """Generate trending price data"""
    import random

    random.seed(42)
    prices = {"open": [], "high": [], "low": [], "close": [], "volume": []}
    price = start
    for _ in range(n):
        o = price
        c = price * (1 + random.gauss(drift, 0.0008))
        h = max(o, c) * (1 + abs(random.gauss(0, 0.0003)))
        l = min(o, c) * (1 - abs(random.gauss(0, 0.0003)))
        prices["open"].append(round(o, 5))
        prices["close"].append(round(c, 5))
        prices["high"].append(round(h, 5))
        prices["low"].append(round(l, 5))
        prices["volume"].append(round(100000 * (1 + random.gauss(0, 0.3))))
        price = c
    return prices


def generate_ranging_data(n=500, center=1.0850, width=0.005):
    """Generate ranging/mean-reverting price data"""
    import random

    random.seed(99)
    prices = {"open": [], "high": [], "low": [], "close": [], "volume": []}
    price = center
    for _ in range(n):
        # Mean revert toward center
        revert = (center - price) * 0.05
        o = price
        c = price + revert + random.gauss(0, width * 0.1)
        h = max(o, c) * (1 + abs(random.gauss(0, 0.0002)))
        l = min(o, c) * (1 - abs(random.gauss(0, 0.0002)))
        prices["open"].append(round(o, 5))
        prices["close"].append(round(c, 5))
        prices["high"].append(round(h, 5))
        prices["low"].append(round(l, 5))
        prices["volume"].append(round(100000 * (1 + random.gauss(0, 0.3))))
        price = c
    return prices


def log_partial_conditions_mrb(strategy, ohlcv_data, regime, bar_idx):
    """Log which MRB sub-conditions pass/fail at a given bar"""
    close = ohlcv_data["close"]
    high = ohlcv_data["high"]
    low = ohlcv_data["low"]

    if bar_idx < strategy.bb_period:
        return None

    # Calculate indicators up to this bar using pandas_ta
    try:
        import pandas as pd
        import pandas_ta as ta

        df = pd.DataFrame(
            {
                "open": ohlcv_data["open"][: bar_idx + 1],
                "high": ohlcv_data["high"][: bar_idx + 1],
                "low": ohlcv_data["low"][: bar_idx + 1],
                "close": ohlcv_data["close"][: bar_idx + 1],
                "volume": ohlcv_data["volume"][: bar_idx + 1],
            }
        )
        bb = ta.bbands(df["close"], length=strategy.bb_period, std=strategy.bb_std)
        adx_df = ta.adx(df["high"], df["low"], df["close"], length=strategy.adx_period)
        stoch = ta.stoch(
            df["high"],
            df["low"],
            df["close"],
            k=strategy.stoch_k_period,
            d=strategy.stoch_d_period,
            smooth_k=strategy.stoch_smooth,
        )
        rsi = ta.rsi(df["close"], length=strategy.rsi_period)
    except ImportError:
        return None

    if bb is None or adx_df is None or rsi is None:
        return None

    current_price = Decimal(str(close[bar_idx]))
    # pandas_ta BB column names vary by version — find them dynamically
    bb_cols = list(bb.columns)
    bb_upper = Decimal(str(bb[bb_cols[2]].iloc[-1]))  # BBU is typically 3rd column
    bb_lower = Decimal(str(bb[bb_cols[0]].iloc[-1]))  # BBL is typically 1st column
    bb_middle = Decimal(str(bb[bb_cols[1]].iloc[-1]))  # BBM is typically 2nd column
    adx_cols = list(adx_df.columns)
    adx = float(adx_df[adx_cols[0]].iloc[-1])  # ADX is typically 1st column
    stoch_k = float(stoch.iloc[:, 0].iloc[-1]) if stoch is not None else 50
    rsi_val = float(rsi.iloc[-1])

    # Evaluate conditions
    long_conds = {
        "adx_low": adx < strategy.adx_threshold,
        "price_below_bb": current_price < bb_lower,
        "stoch_oversold": stoch_k < strategy.stoch_oversold,
        "rsi_oversold": rsi_val < strategy.rsi_oversold,
    }
    short_conds = {
        "adx_low": adx < strategy.adx_threshold,
        "price_above_bb": current_price > bb_upper,
        "stoch_overbought": stoch_k > strategy.stoch_overbought,
        "rsi_overbought": rsi_val > strategy.rsi_overbought,
    }

    long_met = sum(long_conds.values())
    short_met = sum(short_conds.values())

    return {
        "bar": bar_idx,
        "price": float(current_price),
        "adx": adx,
        "stoch_k": stoch_k,
        "rsi": rsi_val,
        "bb_lower": float(bb_lower),
        "bb_upper": float(bb_upper),
        "bb_middle": float(bb_middle),
        "long_conds": long_conds,
        "short_conds": short_conds,
        "long_met": long_met,
        "short_met": short_met,
        "adx_gap": strategy.adx_threshold - adx,
        "stoch_long_gap": strategy.stoch_oversold - stoch_k,
        "rsi_long_gap": strategy.rsi_oversold - rsi_val,
        "stoch_short_gap": stoch_k - strategy.stoch_overbought,
        "rsi_short_gap": rsi_val - strategy.rsi_overbought,
    }


def run_mrb_diagnostic():
    """Run MRB through actual generate_signal() on both data types"""
    print("=" * 70)
    print("  MRB Diagnostic — Actual generate_signal() method")
    print("=" * 70)

    mrb = MeanReversionBollinger()
    regimes = {
        "trending": RegimeType.TREND_STRONG_UP,
        "ranging": RegimeType.RANGE_BOUND,
    }

    datasets = {
        "trending": generate_trending_data(500),
        "ranging": generate_ranging_data(500),
    }

    for data_name, ohlcv in datasets.items():
        regime = regimes[data_name]
        print(f"\n  --- {data_name.upper()} data (regime={regime.value}) ---")

        signals_found = 0
        bars_checked = 0
        partial_long = 0
        partial_short = 0

        for i in range(mrb.bb_period, len(ohlcv["close"])):
            bars_checked += 1
            bar_data = {k: v[: i + 1] for k, v in ohlcv.items()}
            signal = mrb.generate_signal("EURUSD", bar_data, regime=regime)

            if signal:
                signals_found += 1
                if signal.signal_type == SignalType.BUY:
                    print(
                        f"  Bar {i}: BUY  conf={signal.confidence:.2f} "
                        f"entry={signal.entry_price} sl={signal.stop_loss} tp={signal.take_profit}"
                    )
                else:
                    print(
                        f"  Bar {i}: SELL conf={signal.confidence:.2f} "
                        f"entry={signal.entry_price} sl={signal.stop_loss} tp={signal.take_profit}"
                    )

            # Log partial conditions every 50 bars
            if i % 50 == 0:
                info = log_partial_conditions_mrb(mrb, ohlcv, regime, i)
                if info:
                    lm = info["long_met"]
                    sm = info["short_met"]
                    if lm >= 2:
                        partial_long += 1
                    if sm >= 2:
                        partial_short += 1

                    if lm >= 2 or sm >= 2:
                        print(
                            f"  Bar {i}: PARTIAL long={lm}/4 short={sm}/4 "
                            f"adx={info['adx']:.1f}(gap={info['adx_gap']:.1f}) "
                            f"stoch={info['stoch_k']:.1f} rsi={info['rsi']:.1f} "
                            f"price={info['price']:.5f} "
                            f"bbL={info['bb_lower']:.5f} bbU={info['bb_upper']:.5f}"
                        )

                        # Show which conditions failed
                        for name, met in info["long_conds"].items():
                            if not met:
                                print(f"    LONG fail: {name}")
                        for name, met in info["short_conds"].items():
                            if not met:
                                print(f"    SHORT fail: {name}")

        print(f"\n  Summary ({data_name}): {signals_found} signals from {bars_checked} bars")
        print(f"  Partial long hits (>=2/4): {partial_long}")
        print(f"  Partial short hits (>=2/4): {partial_short}")


def log_partial_conditions_mlb(strategy, ohlcv_data, bar_idx):
    """Log which MLB sub-conditions pass/fail at a given bar"""
    close = ohlcv_data["close"]
    high = ohlcv_data["high"]
    low = ohlcv_data["low"]
    volume = ohlcv_data["volume"]

    if bar_idx < strategy.lookback_period + 5:
        return None

    current_price = close[bar_idx]
    prev_close = close[bar_idx - 1]
    current_vol = volume[bar_idx]

    recent_high = max(high[bar_idx - strategy.lookback_period : bar_idx])
    recent_low = min(low[bar_idx - strategy.lookback_period : bar_idx])

    long_breakout = current_price > recent_high and prev_close <= recent_high
    short_breakout = current_price < recent_low and prev_close >= recent_low

    avg_volume = sum(volume[bar_idx - strategy.lookback_period : bar_idx]) / strategy.lookback_period
    vol_ratio = current_vol / avg_volume if avg_volume > 0 else 0
    volume_ok = current_vol >= avg_volume * strategy.volume_mult

    return {
        "bar": bar_idx,
        "price": current_price,
        "recent_high": recent_high,
        "recent_low": recent_low,
        "long_breakout": long_breakout,
        "short_breakout": short_breakout,
        "volume_ratio": vol_ratio,
        "volume_ok": volume_ok,
        "vol_gap": strategy.volume_mult - vol_ratio,
        "any_breakout": long_breakout or short_breakout,
    }


def run_mlb_diagnostic():
    """Run MLB through actual generate_signal() on both data types"""
    print("\n" + "=" * 70)
    print("  MLB Diagnostic — Actual generate_signal() method")
    print("=" * 70)

    mlb = MLBreakout(model=None)  # No model, uses heuristic fallback
    regimes = {
        "trending": RegimeType.TREND_STRONG_UP,
        "ranging": RegimeType.RANGE_BOUND,
    }

    datasets = {
        "trending": generate_trending_data(500),
        "ranging": generate_ranging_data(500),
    }

    for data_name, ohlcv in datasets.items():
        regime = regimes[data_name]
        print(f"\n  --- {data_name.upper()} data (regime={regime.value}) ---")

        signals_found = 0
        bars_checked = 0
        breakout_count = 0
        vol_fail_count = 0

        for i in range(mlb.lookback_period + 5, len(ohlcv["close"])):
            bars_checked += 1
            bar_data = {k: v[: i + 1] for k, v in ohlcv.items()}
            signal = mlb.generate_signal("EURUSD", bar_data, regime=regime)

            if signal:
                signals_found += 1
                print(
                    f"  Bar {i}: {signal.signal_type.value} conf={signal.confidence:.2f} "
                    f"entry={signal.entry_price} notes={signal.notes}"
                )

            # Log partial conditions every 30 bars
            if i % 30 == 0:
                info = log_partial_conditions_mlb(mlb, ohlcv, i)
                if info:
                    if info["any_breakout"]:
                        breakout_count += 1
                        print(
                            f"  Bar {i}: BREAKOUT {'long' if info['long_breakout'] else 'short'} "
                            f"price={info['price']:.5f} "
                            f"high={info['recent_high']:.5f} low={info['recent_low']:.5f}"
                        )
                        if not info["volume_ok"]:
                            vol_fail_count += 1
                            print(f"    Volume FAIL: ratio={info['volume_ratio']:.2f} " f"need>={mlb.volume_mult:.1f}")

        print(f"\n  Summary ({data_name}): {signals_found} signals from {bars_checked} bars")
        print(f"  Breakout bars found: {breakout_count}")
        print(f"  Volume confirm failures: {vol_fail_count}")


if __name__ == "__main__":
    run_mrb_diagnostic()
    run_mlb_diagnostic()
    print("\n" + "=" * 70)
    print("  Diagnostic complete")
    print("=" * 70)
