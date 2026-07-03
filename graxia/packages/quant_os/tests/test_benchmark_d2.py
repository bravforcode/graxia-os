"""
D2: Performance benchmark — Pure Python vs Numba JIT indicator calculation.
Isolates indicator computation for 125k synthetic XAUUSD M15 bars.
"""

import json
import time
from datetime import UTC, datetime
from pathlib import Path

import numpy as np

from graxia.packages.quant_os.backtest.engine import (
    _indicators_numba_impl,
)

BARS = 125_000
ARTIFACT_DIR = Path(__file__).resolve().parent.parent / "artifacts" / "benchmarks"


def _ema_python(close, length):
    """Pure Python EMA (no numba)."""
    n = len(close)
    out = np.full(n, np.nan)
    if n < length:
        return out
    alpha = 2.0 / (length + 1.0)
    sma = 0.0
    for i in range(length):
        sma += close[i]
    sma /= length
    out[length - 1] = sma
    for i in range(length, n):
        out[i] = close[i] * alpha + out[i - 1] * (1.0 - alpha)
    return out


def _rsi_python(close, length):
    """Pure Python RSI."""
    n = len(close)
    out = np.full(n, np.nan)
    if n < length + 1:
        return out
    gains = np.zeros(length)
    losses = np.zeros(length)
    for i in range(1, length + 1):
        diff = close[i] - close[i - 1]
        if diff > 0:
            gains[i - 1] = diff
        else:
            losses[i - 1] = -diff
    avg_gain = 0.0
    avg_loss = 0.0
    for i in range(length):
        avg_gain += gains[i]
        avg_loss += losses[i]
    avg_gain /= length
    avg_loss /= length
    if avg_loss == 0:
        out[length] = 100.0
    else:
        rs = avg_gain / avg_loss
        out[length] = 100.0 - 100.0 / (1.0 + rs)
    for i in range(length + 1, n):
        diff = close[i] - close[i - 1]
        if diff > 0:
            avg_gain = (avg_gain * (length - 1) + diff) / length
            avg_loss = (avg_loss * (length - 1)) / length
        else:
            avg_gain = (avg_gain * (length - 1)) / length
            avg_loss = (avg_loss * (length - 1) - diff) / length
        if avg_loss == 0:
            out[i] = 100.0
        else:
            rs = avg_gain / avg_loss
            out[i] = 100.0 - 100.0 / (1.0 + rs)
    return out


def _atr_python(high, low, close, length):
    """Pure Python ATR."""
    n = len(close)
    out = np.full(n, np.nan)
    if n < length + 1:
        return out
    tr = np.zeros(n)
    tr[0] = high[0] - low[0]
    for i in range(1, n):
        hl = high[i] - low[i]
        hc = abs(high[i] - close[i - 1])
        lc = abs(low[i] - close[i - 1])
        tr[i] = max(hl, max(hc, lc))
    atr_val = 0.0
    for i in range(length):
        atr_val += tr[i]
    atr_val /= length
    out[length - 1] = atr_val
    for i in range(length, n):
        atr_val = (atr_val * (length - 1) + tr[i]) / length
        out[i] = atr_val
    return out


def _indicators_python_impl(close, high, low, vol):
    """Pure Python indicator batch — same logic as _indicators_numba_impl, no JIT."""
    result = {}
    result["ema_9"] = _ema_python(close, 9)
    result["ema_20"] = _ema_python(close, 20)
    result["ema_50"] = _ema_python(close, 50)
    result["ema_200"] = _ema_python(close, 200)
    result["rsi_14"] = _rsi_python(close, 14)
    result["atr_14"] = _atr_python(high, low, close, 14)
    n = len(vol)
    vol_sma = np.full(n, np.nan)
    for i in range(19, n):
        s = 0.0
        for j in range(i - 19, i + 1):
            s += vol[j]
        vol_sma[i] = s / 20.0
    result["volume_sma_20"] = vol_sma
    return result


def generate_synthetic_ohlcv(n: int) -> dict[str, np.ndarray]:
    rng = np.random.default_rng(42)
    close = np.cumsum(rng.normal(0, 0.5, n)) + 2300.0
    high = close + rng.uniform(0.5, 3.0, n)
    low = close - rng.uniform(0.5, 3.0, n)
    open_ = close + rng.normal(0, 0.3, n)
    volume = rng.uniform(50, 500, n)
    return {
        "open": open_.astype(np.float64),
        "high": high.astype(np.float64),
        "low": low.astype(np.float64),
        "close": close.astype(np.float64),
        "volume": volume.astype(np.float64),
    }


def main():
    print(f"Generating {BARS:,} synthetic bars...")
    data = generate_synthetic_ohlcv(BARS)

    close_arr = data["close"]
    high_arr = data["high"]
    low_arr = data["low"]
    vol_arr = data["volume"]

    # Warmup numba JIT
    print("Warming up Numba JIT (compile step)...")
    _indicators_numba_impl(close_arr[:200], high_arr[:200], low_arr[:200], vol_arr[:200])

    # Numba path
    print("Benchmarking Numba JIT path...")
    t0 = time.perf_counter()
    nb_result = _indicators_numba_impl(close_arr, high_arr, low_arr, vol_arr)
    nb_time = time.perf_counter() - t0

    # Pure Python path
    print("Benchmarking pure Python (no JIT) path...")
    t0 = time.perf_counter()
    py_result = _indicators_python_impl(close_arr, high_arr, low_arr, vol_arr)
    py_time = time.perf_counter() - t0

    speedup = round(py_time / nb_time, 2) if nb_time > 0 else 0
    bars_per_sec_nb = BARS / nb_time if nb_time > 0 else 0
    bars_per_sec_py = BARS / py_time if py_time > 0 else 0

    report = {
        "benchmark": "D2_pure_python_vs_numba",
        "bars": BARS,
        "symbol": "XAUUSD",
        "timeframe": "M15",
        "results": {
            "pure_python": {
                "label": "pure_python",
                "total_bars": BARS,
                "elapsed_s": round(py_time, 4),
                "bars_per_sec": round(bars_per_sec_py, 1),
            },
            "numba_jit": {
                "label": "numba_jit",
                "total_bars": BARS,
                "elapsed_s": round(nb_time, 4),
                "bars_per_sec": round(bars_per_sec_nb, 1),
            },
            "speedup": speedup,
        },
        "timestamp": datetime.now(UTC).isoformat() + "Z",
    }

    print(f"\n{'='*50}")
    print(f"Pure Python (no JIT) : {py_time:.2f}s  ({bars_per_sec_py:,.0f} bars/s)")
    print(f"Numba JIT            : {nb_time:.2f}s  ({bars_per_sec_nb:,.0f} bars/s)")
    print(f"Speedup              : {speedup:.2f}x")
    print(f"{'='*50}")

    ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)
    out = ARTIFACT_DIR / "numba_comparison.json"
    out.write_text(json.dumps(report, indent=2))
    print(f"\nSaved to {out}")


def test_benchmark_d2_numba_vs_python():
    """D2: Benchmark pure Python vs Numba JIT indicator paths (125k bars)."""
    main()


if __name__ == "__main__":
    main()
