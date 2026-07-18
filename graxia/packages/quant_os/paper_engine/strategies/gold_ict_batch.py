"""
Vectorized Gold ICT Signal Generators — O(n) per strategy.

Each function takes numpy arrays and returns a (n,) int array of signals:
  0 = no signal, 1 = BUY, -1 = SELL

Plus SL/TP arrays for each bar.

These replicate the gold_bot strategy logic but compute indicators ONCE,
making them suitable for WFA/DK-test on large datasets (50K+ bars).
"""
from __future__ import annotations

import numpy as np
from typing import NamedTuple


class BatchSignals(NamedTuple):
    """Vectorized signal output."""
    directions: np.ndarray   # (n,) int: 0/1/-1
    sl: np.ndarray           # (n,) float: stop loss price
    tp: np.ndarray           # (n,) float: take profit price
    scores: np.ndarray       # (n,) int: 0-100 score


def _ema(prices: np.ndarray, period: int) -> np.ndarray:
    """Vectorized EMA — returns same length as input, NaN for first period-1 bars."""
    n = len(prices)
    out = np.full(n, np.nan)
    if n < period:
        return out
    alpha = 2.0 / (period + 1)
    out[period - 1] = np.mean(prices[:period])
    for i in range(period, n):
        out[i] = prices[i] * alpha + out[i - 1] * (1 - alpha)
    return out


def _rsi(prices: np.ndarray, period: int = 14) -> np.ndarray:
    """Vectorized RSI."""
    n = len(prices)
    out = np.full(n, np.nan)
    if n < period + 1:
        return out
    deltas = np.diff(prices)
    gains = np.where(deltas > 0, deltas, 0.0)
    losses = np.where(deltas < 0, -deltas, 0.0)
    avg_gain = np.mean(gains[:period])
    avg_loss = np.mean(losses[:period])
    for i in range(period, len(deltas)):
        avg_gain = (avg_gain * (period - 1) + gains[i]) / period
        avg_loss = (avg_loss * (period - 1) + losses[i]) / period
        if avg_loss == 0:
            out[i + 1] = 100.0
        else:
            rs = avg_gain / avg_loss
            out[i + 1] = 100.0 - (100.0 / (1.0 + rs))
    return out


def _atr(high: np.ndarray, low: np.ndarray, close: np.ndarray, period: int = 14) -> np.ndarray:
    """Vectorized ATR."""
    n = len(close)
    out = np.full(n, np.nan)
    if n < period + 1:
        return out
    tr = np.maximum(
        high[1:] - low[1:],
        np.maximum(
            np.abs(high[1:] - close[:-1]),
            np.abs(low[1:] - close[:-1]),
        ),
    )
    out[period] = np.mean(tr[:period])
    for i in range(period, len(tr)):
        out[i + 1] = (out[i] * (period - 1) + tr[i]) / period
    return out


def batch_ema_cross(
    close: np.ndarray, high: np.ndarray, low: np.ndarray,
    fast: int = 9, slow: int = 21, trend: int = 50,
) -> BatchSignals:
    """EMA 9/21 crossover with EMA50 trend filter."""
    n = len(close)
    dirs = np.zeros(n, dtype=int)
    sl = np.zeros(n)
    tp = np.zeros(n)
    scores = np.zeros(n, dtype=int)

    ema_f = _ema(close, fast)
    ema_s = _ema(close, slow)
    ema_t = _ema(close, trend)
    atr = _atr(high, low, close)

    for i in range(slow + 1, n):
        if np.isnan(ema_f[i]) or np.isnan(ema_s[i]):
            continue
        prev_diff = ema_f[i - 1] - ema_s[i - 1]
        curr_diff = ema_f[i] - ema_s[i]
        a = atr[i] if not np.isnan(atr[i]) else 5.0

        if prev_diff <= 0 and curr_diff > 0:
            dirs[i] = 1
            scores[i] = 60
            if not np.isnan(ema_t[i]) and close[i] > ema_t[i]:
                scores[i] += 15
            sl[i] = close[i] - a * 1.5
            tp[i] = close[i] + a * 3.0
        elif prev_diff >= 0 and curr_diff < 0:
            dirs[i] = -1
            scores[i] = 60
            if not np.isnan(ema_t[i]) and close[i] < ema_t[i]:
                scores[i] += 15
            sl[i] = close[i] + a * 1.5
            tp[i] = close[i] - a * 3.0

    return BatchSignals(dirs, sl, tp, scores)


def batch_bos_choch(
    close: np.ndarray, high: np.ndarray, low: np.ndarray,
    swing_lookback: int = 3,
) -> BatchSignals:
    """Break of Structure / Change of Character — precompute swings once."""
    n = len(close)
    dirs = np.zeros(n, dtype=int)
    sl_arr = np.zeros(n)
    tp_arr = np.zeros(n)
    scores = np.zeros(n, dtype=int)

    # Precompute all swing highs and lows (O(n) once)
    swing_highs = []  # list of (idx, price)
    swing_lows = []
    lb = swing_lookback
    for i in range(lb, n - lb):
        if all(high[i] > high[i - j] and high[i] > high[i + j] for j in range(1, lb + 1)):
            swing_highs.append((i, high[i]))
        if all(low[i] < low[i - j] and low[i] < low[i + j] for j in range(1, lb + 1)):
            swing_lows.append((i, low[i]))

    # For each bar, find the most recent swing high/low before it
    sh_arr = np.full(n, np.nan)
    sl_price_arr = np.full(n, np.nan)
    for idx, price in swing_highs:
        sh_arr[idx] = price
    for idx, price in swing_lows:
        sl_price_arr[idx] = price

    # Forward-fill to get "current" swing levels at each bar
    last_sh = np.nan
    last_sl = np.nan
    for i in range(n):
        if not np.isnan(sh_arr[i]):
            last_sh = sh_arr[i]
        if not np.isnan(sl_price_arr[i]):
            last_sl = sl_price_arr[i]
        sh_arr[i] = last_sh
        sl_price_arr[i] = last_sl

    # Generate signals
    for i in range(max(lb * 2 + 1, 30), n):
        if np.isnan(sh_arr[i]) or np.isnan(sl_price_arr[i]):
            continue
        last_sh = sh_arr[i]
        last_sl = sl_price_arr[i]

        if close[i] > last_sh:
            dirs[i] = 1
            scores[i] = 70
            sl_arr[i] = (close[i] + last_sl) / 2
            tp_arr[i] = close[i] + (close[i] - sl_arr[i]) * 2.5
        elif close[i] < last_sl:
            dirs[i] = -1
            scores[i] = 70
            sl_arr[i] = (close[i] + last_sh) / 2
            tp_arr[i] = close[i] - (sl_arr[i] - close[i]) * 2.5

    return BatchSignals(dirs, sl_arr, tp_arr, scores)


def batch_fvg(
    close: np.ndarray, high: np.ndarray, low: np.ndarray,
    lookback: int = 25, buffer: float = 5.0,
) -> BatchSignals:
    """Fair Value Gap — detect FVG zones and check price proximity."""
    n = len(close)
    dirs = np.zeros(n, dtype=int)
    sl_arr = np.zeros(n)
    tp_arr = np.zeros(n)
    scores = np.zeros(n, dtype=int)

    for i in range(30, n):
        # Scan last lookback bars for FVGs
        start = max(3, i - lookback)
        for j in range(i - 3, start - 1, -1):
            if j + 2 >= n:
                continue
            # Bullish FVG: low[j] > high[j+2]
            if low[j] > high[j + 2]:
                fvg_top = low[j]
                fvg_bottom = high[j + 2]
                if fvg_bottom - buffer <= close[i] <= fvg_top + buffer:
                    dirs[i] = 1
                    scores[i] = 75
                    sl_arr[i] = fvg_bottom - 10
                    tp_arr[i] = close[i] + (close[i] - fvg_bottom) * 2.0
                    break
            # Bearish FVG: low[j+2] > high[j]
            if j + 2 < n and low[j + 2] > high[j]:
                fvg_top = low[j + 2]
                fvg_bottom = high[j]
                if fvg_bottom - buffer <= close[i] <= fvg_top + buffer:
                    dirs[i] = -1
                    scores[i] = 75
                    sl_arr[i] = fvg_top + 10
                    tp_arr[i] = close[i] - (fvg_top - close[i]) * 2.0
                    break

    return BatchSignals(dirs, sl_arr, tp_arr, scores)


def batch_rsi(
    close: np.ndarray, high: np.ndarray, low: np.ndarray,
    period: int = 14,
) -> BatchSignals:
    """RSI overbought/oversold signals."""
    n = len(close)
    dirs = np.zeros(n, dtype=int)
    sl_arr = np.zeros(n)
    tp_arr = np.zeros(n)
    scores = np.zeros(n, dtype=int)

    rsi = _rsi(close, period)
    atr = _atr(high, low, close)

    for i in range(period + 1, n):
        if np.isnan(rsi[i]):
            continue
        a = atr[i] if not np.isnan(atr[i]) else 5.0
        if rsi[i] < 25:
            dirs[i] = 1
            scores[i] = 80
            sl_arr[i] = close[i] - a * 1.5
            tp_arr[i] = close[i] + a * 2.5
        elif rsi[i] < 35:
            dirs[i] = 1
            scores[i] = 65
            sl_arr[i] = close[i] - a * 1.5
            tp_arr[i] = close[i] + a * 2.5
        elif rsi[i] > 75:
            dirs[i] = -1
            scores[i] = 80
            sl_arr[i] = close[i] + a * 1.5
            tp_arr[i] = close[i] - a * 2.5
        elif rsi[i] > 65:
            dirs[i] = -1
            scores[i] = 65
            sl_arr[i] = close[i] + a * 1.5
            tp_arr[i] = close[i] - a * 2.5

    return BatchSignals(dirs, sl_arr, tp_arr, scores)


def batch_supply_demand(
    close: np.ndarray, high: np.ndarray, low: np.ndarray,
    volume: np.ndarray | None = None,
    zone_pct: float = 0.12,
) -> BatchSignals:
    """Supply/demand zone detection — rolling 20-bar zones."""
    n = len(close)
    dirs = np.zeros(n, dtype=int)
    sl_arr = np.zeros(n)
    tp_arr = np.zeros(n)
    scores = np.zeros(n, dtype=int)
    atr = _atr(high, low, close)

    for i in range(50, n):
        recent_lows = low[i - 20:i]
        recent_highs = high[i - 20:i]
        avg_low = np.mean(recent_lows)
        avg_high = np.mean(recent_highs)
        zone_range = avg_high - avg_low
        if zone_range <= 0:
            continue
        a = atr[i] if not np.isnan(atr[i]) else 10.0
        sl_dist = max(a * 1.5, 28.0)

        if (close[i] - avg_low) / zone_range < zone_pct:
            dirs[i] = 1
            scores[i] = 70
            sl_arr[i] = close[i] - sl_dist
            tp_arr[i] = close[i] + sl_dist * 1.5
        elif (avg_high - close[i]) / zone_range < zone_pct:
            dirs[i] = -1
            scores[i] = 70
            sl_arr[i] = close[i] + sl_dist
            tp_arr[i] = close[i] - sl_dist * 1.5

        # Volume confirmation
        if volume is not None and i >= 20:
            avg_vol = np.mean(volume[i - 20:i])
            if avg_vol > 0 and volume[i] > avg_vol * 1.4:
                scores[i] += 10

    return BatchSignals(dirs, sl_arr, tp_arr, scores)


def batch_london_breakout(
    close: np.ndarray, high: np.ndarray, low: np.ndarray,
    volume: np.ndarray | None = None,
) -> BatchSignals:
    """London session breakout — range of bars [-20:-16] as London range."""
    n = len(close)
    dirs = np.zeros(n, dtype=int)
    sl_arr = np.zeros(n)
    tp_arr = np.zeros(n)
    scores = np.zeros(n, dtype=int)

    for i in range(20, n):
        london_high = np.max(high[i - 20:i - 16])
        london_low = np.min(low[i - 20:i - 16])
        range_size = london_high - london_low
        if range_size <= 0:
            continue

        if close[i] > london_high:
            dirs[i] = 1
            scores[i] = 65
            sl_arr[i] = london_low
            tp_arr[i] = close[i] + range_size * 2.5
        elif close[i] < london_low:
            dirs[i] = -1
            scores[i] = 65
            sl_arr[i] = london_high
            tp_arr[i] = close[i] - range_size * 2.5

        if volume is not None and i >= 20:
            avg_vol = np.mean(volume[i - 20:i])
            if avg_vol > 0 and volume[i] > avg_vol * 1.3:
                scores[i] += 10

    return BatchSignals(dirs, sl_arr, tp_arr, scores)


def batch_vwap_rejection(
    close: np.ndarray, high: np.ndarray, low: np.ndarray,
    volume: np.ndarray | None = None,
) -> BatchSignals:
    """VWAP rejection — price crosses VWAP level."""
    n = len(close)
    dirs = np.zeros(n, dtype=int)
    sl_arr = np.zeros(n)
    tp_arr = np.zeros(n)
    scores = np.zeros(n, dtype=int)

    if volume is None:
        volume = np.ones(n)

    atr = _atr(high, low, close)
    typical = (high + low + close) / 3.0
    cum_tp_vol = np.cumsum(typical * volume)
    cum_vol = np.cumsum(volume)

    for i in range(20, n):
        if cum_vol[i] <= 0:
            continue
        vwap = cum_tp_vol[i] / cum_vol[i]
        if vwap <= 0:
            continue
        distance = (close[i] - vwap) / vwap * 100
        a = atr[i] if not np.isnan(atr[i]) else 5.0

        if abs(distance) < 0.05 and i >= 1:
            prev_dist = (close[i - 1] - vwap) / vwap * 100 if i >= 1 else 0
            if prev_dist > 0.05 and distance <= 0.05:
                dirs[i] = -1
                scores[i] = 70
                sl_arr[i] = close[i] + a * 1.5
                tp_arr[i] = close[i] - a * 2.0
            elif prev_dist < -0.05 and distance >= -0.05:
                dirs[i] = 1
                scores[i] = 70
                sl_arr[i] = close[i] - a * 1.5
                tp_arr[i] = close[i] + a * 2.0

        if volume is not None and i >= 20:
            avg_vol = np.mean(volume[i - 20:i])
            if avg_vol > 0 and volume[i] > avg_vol * 1.2:
                scores[i] += 10

    return BatchSignals(dirs, sl_arr, tp_arr, scores)


def batch_liquidity_sweep(
    close: np.ndarray, high: np.ndarray, low: np.ndarray,
    lookback: int = 20, tolerance: float = 0.0005,
) -> BatchSignals:
    """Liquidity sweep — detect equal highs/lows and sweep."""
    n = len(close)
    dirs = np.zeros(n, dtype=int)
    sl_arr = np.zeros(n)
    tp_arr = np.zeros(n)
    scores = np.zeros(n, dtype=int)
    atr = _atr(high, low, close)

    for i in range(30, n):
        a = atr[i] if not np.isnan(atr[i]) else 5.0
        sl_buffer = a * 0.5
        start = max(5, i - lookback)

        for j in range(i - 5, start - 1, -1):
            if j < 0:
                continue
            # Equal highs (buy-side liquidity)
            if high[i] > 0 and abs(high[i] - high[j]) / high[i] < tolerance:
                sweep_high = np.max(high[min(i, j):max(i, j) + 1])
                if sweep_high > high[i] and close[i] < high[i]:
                    dirs[i] = -1
                    scores[i] = 80
                    sl_arr[i] = sweep_high + sl_buffer
                    tp_arr[i] = close[i] - (sl_arr[i] - close[i]) * 2.5
                    break

            # Equal lows (sell-side liquidity)
            if low[i] > 0 and abs(low[i] - low[j]) / low[i] < tolerance:
                sweep_low = np.min(low[min(i, j):max(i, j) + 1])
                if sweep_low < low[i] and close[i] > low[i]:
                    dirs[i] = 1
                    scores[i] = 80
                    sl_arr[i] = sweep_low - sl_buffer
                    tp_arr[i] = close[i] + (close[i] - sl_arr[i]) * 2.5
                    break

        if scores[i] > 0:
            continue

    return BatchSignals(dirs, sl_arr, tp_arr, scores)


def batch_multi_tf_align(
    close: np.ndarray, high: np.ndarray, low: np.ndarray,
) -> BatchSignals:
    """Multi-timeframe EMA alignment — single TF proxy (EMA20/50 alignment)."""
    n = len(close)
    dirs = np.zeros(n, dtype=int)
    sl_arr = np.zeros(n)
    tp_arr = np.zeros(n)
    scores = np.zeros(n, dtype=int)

    ema20 = _ema(close, 20)
    ema50 = _ema(close, 50)
    atr = _atr(high, low, close)

    for i in range(50, n):
        if np.isnan(ema20[i]) or np.isnan(ema50[i]):
            continue
        a = atr[i] if not np.isnan(atr[i]) else 5.0

        if close[i] > ema20[i] > ema50[i]:
            dirs[i] = 1
            scores[i] = 85
            sl_arr[i] = close[i] - a * 3.0
            tp_arr[i] = close[i] + a * 4.5
        elif close[i] < ema20[i] < ema50[i]:
            dirs[i] = -1
            scores[i] = 85
            sl_arr[i] = close[i] + a * 3.0
            tp_arr[i] = close[i] - a * 4.5

    return BatchSignals(dirs, sl_arr, tp_arr, scores)


def batch_fibonacci(
    close: np.ndarray, high: np.ndarray, low: np.ndarray,
    lookback: int = 50, proximity_pct: float = 0.003,
) -> BatchSignals:
    """Fibonacci retracement — 50-bar swing levels."""
    n = len(close)
    dirs = np.zeros(n, dtype=int)
    sl_arr = np.zeros(n)
    tp_arr = np.zeros(n)
    scores = np.zeros(n, dtype=int)
    atr = _atr(high, low, close)

    for i in range(lookback, n):
        swing_high = np.max(high[i - lookback:i])
        swing_low = np.min(low[i - lookback:i])
        rng = swing_high - swing_low
        if rng <= 0:
            continue

        fib_618 = swing_high - rng * 0.618
        fib_500 = swing_high - rng * 0.500
        fib_382 = swing_high - rng * 0.382
        a = atr[i] if not np.isnan(atr[i]) else 8.0

        if close[i] > 0 and abs(close[i] - fib_618) / close[i] < proximity_pct:
            scores[i] = 75
            dirs[i] = 1 if close[i] >= fib_618 else -1
            if dirs[i] == 1:
                sl_arr[i] = fib_618 - a * 0.5
                tp_arr[i] = fib_500
            else:
                sl_arr[i] = fib_382 + a * 0.5
                tp_arr[i] = fib_500
        elif close[i] > 0 and abs(close[i] - fib_500) / close[i] < proximity_pct:
            scores[i] = 65
            dirs[i] = 1 if close[i] >= fib_500 else -1
            if dirs[i] == 1:
                sl_arr[i] = fib_618 - a * 0.5
                tp_arr[i] = fib_382
            else:
                sl_arr[i] = fib_382 + a * 0.5
                tp_arr[i] = fib_618
        elif close[i] > 0 and abs(close[i] - fib_382) / close[i] < proximity_pct:
            scores[i] = 55
            dirs[i] = 1 if close[i] >= fib_382 else -1
            if dirs[i] == 1:
                sl_arr[i] = fib_500 - a * 0.5
                tp_arr[i] = fib_500
            else:
                sl_arr[i] = fib_500 + a * 0.5
                tp_arr[i] = fib_500

    return BatchSignals(dirs, sl_arr, tp_arr, scores)


def batch_order_block(
    close: np.ndarray, high: np.ndarray, low: np.ndarray,
    proximity_pct: float = 0.002,
) -> BatchSignals:
    """Order Block — last bearish candle before rally (or vice versa)."""
    n = len(close)
    dirs = np.zeros(n, dtype=int)
    sl_arr = np.zeros(n)
    tp_arr = np.zeros(n)
    scores = np.zeros(n, dtype=int)

    for i in range(50, n):
        start = max(5, i - 20)
        for j in range(i - 5, start - 1, -1):
            if j < 1 or j + 1 >= n:
                continue
            # Bullish OB: bearish candle followed by bullish move
            if close[j] < close[j - 1] and close[j + 1] > close[j]:
                ob_top = high[j]
                ob_bottom = low[j]
                if close[i] > 0 and abs(close[i] - ob_top) / close[i] < proximity_pct:
                    dirs[i] = 1
                    scores[i] = 75
                    sl_arr[i] = ob_bottom - 5
                    tp_arr[i] = close[i] + (close[i] - sl_arr[i]) * 2
                    break
        if scores[i] > 0:
            continue
        for j in range(i - 5, start - 1, -1):
            if j < 1 or j + 1 >= n:
                continue
            # Bearish OB: bullish candle followed by bearish move
            if close[j] > close[j - 1] and close[j + 1] < close[j]:
                ob_top = high[j]
                ob_bottom = low[j]
                if close[i] > 0 and abs(close[i] - ob_bottom) / close[i] < proximity_pct:
                    dirs[i] = -1
                    scores[i] = 75
                    sl_arr[i] = ob_top + 5
                    tp_arr[i] = close[i] - (sl_arr[i] - close[i]) * 2
                    break

    return BatchSignals(dirs, sl_arr, tp_arr, scores)


def batch_news_fade(
    close: np.ndarray, high: np.ndarray, low: np.ndarray,
    spike_threshold: float = 0.4,
) -> BatchSignals:
    """News fade — fade sudden spikes with RSI confirmation."""
    n = len(close)
    dirs = np.zeros(n, dtype=int)
    sl_arr = np.zeros(n)
    tp_arr = np.zeros(n)
    scores = np.zeros(n, dtype=int)

    rsi = _rsi(close, 14)
    atr = _atr(high, low, close)

    for i in range(30, n):
        if close[i - 10] <= 0:
            continue
        recent_move = abs(close[i] - close[i - 10]) / close[i - 10] * 100
        if recent_move <= spike_threshold:
            continue

        a = atr[i] if not np.isnan(atr[i]) else 5.0
        r = rsi[i] if not np.isnan(rsi[i]) else 50.0

        if close[i] > close[i - 10]:
            # Spike up → fade short
            if r > 70:
                dirs[i] = -1
                scores[i] = 75
                sl_arr[i] = close[i] + a * 1.5
                tp_arr[i] = close[i] - a * 2.5
        else:
            # Spike down → fade long
            if r < 30:
                dirs[i] = 1
                scores[i] = 75
                sl_arr[i] = close[i] - a * 1.5
                tp_arr[i] = close[i] + a * 2.5

    return BatchSignals(dirs, sl_arr, tp_arr, scores)


def batch_opening_range(
    close: np.ndarray, high: np.ndarray, low: np.ndarray,
    volume: np.ndarray | None = None,
    opening_bars: int = 12,
) -> BatchSignals:
    """Opening range breakout — first 12 bars define range."""
    n = len(close)
    dirs = np.zeros(n, dtype=int)
    sl_arr = np.zeros(n)
    tp_arr = np.zeros(n)
    scores = np.zeros(n, dtype=int)

    for i in range(max(20, opening_bars + 1), n):
        or_high = np.max(high[i - opening_bars:i])
        or_low = np.min(low[i - opening_bars:i])
        or_range = or_high - or_low
        if or_range <= 0:
            continue

        if close[i] > or_high:
            dirs[i] = 1
            scores[i] = 70
            sl_arr[i] = or_high - or_range * 0.3
            tp_arr[i] = close[i] + or_range * 2.0
        elif close[i] < or_low:
            dirs[i] = -1
            scores[i] = 70
            sl_arr[i] = or_low + or_range * 0.3
            tp_arr[i] = close[i] - or_range * 2.0

        if volume is not None and i >= 20:
            avg_vol = np.mean(volume[i - 20:i])
            if avg_vol > 0 and volume[i] > avg_vol * 1.3:
                scores[i] += 10

    return BatchSignals(dirs, sl_arr, tp_arr, scores)


# ── Registry: maps strategy_id → batch function ──────────────────────────

BATCH_REGISTRY = {
    "gi_ema_cross": batch_ema_cross,
    "gi_bos_choch": batch_bos_choch,
    "gi_fair_value_gap": batch_fvg,
    "gi_rsi_divergence": batch_rsi,
    "gi_supply_demand": batch_supply_demand,
    "gi_london_breakout": batch_london_breakout,
    "gi_vwap_rejection": batch_vwap_rejection,
    "gi_liquidity_sweep": batch_liquidity_sweep,
    "gi_multi_tf_align": batch_multi_tf_align,
    "gi_fibonacci": batch_fibonacci,
    "gi_order_block": batch_order_block,
    "gi_news_fade": batch_news_fade,
    "gi_opening_range": batch_opening_range,
}


def run_batch_signals(
    strategy_id: str,
    close: np.ndarray,
    high: np.ndarray,
    low: np.ndarray,
    volume: np.ndarray | None = None,
    **kwargs,
) -> BatchSignals:
    """Run a batch signal generator by strategy_id."""
    fn = BATCH_REGISTRY.get(strategy_id)
    if fn is None:
        raise ValueError(f"No batch generator for {strategy_id}. Available: {list(BATCH_REGISTRY.keys())}")

    import inspect
    sig = inspect.signature(fn)
    params = set(sig.parameters.keys()) - {"close", "high", "low"}
    call_kwargs = {}
    if "volume" in params and volume is not None:
        call_kwargs["volume"] = volume
    for k, v in kwargs.items():
        if k in params:
            call_kwargs[k] = v

    return fn(close, high, low, **call_kwargs)
