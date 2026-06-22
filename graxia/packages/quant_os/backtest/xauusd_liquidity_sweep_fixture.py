"""XAUUSD M15 fixture for Phase 3B oracle comparison. Frozen, deterministic."""

from datetime import datetime, timedelta

FROZEN_PARAMS = {
    "strategy_type": "sma_crossover",
    "fast_period": 10,
    "slow_period": 30,
    "symbol": "XAUUSD",
    "cash": 10000,
}


def load_xauusd_m15():
    """Return (data_dict, timestamps) — 200 bars of synthetic XAUUSD M15."""
    # ponytail: synthetic data, deterministic via seed
    import random
    random.seed(2025_06_22)

    n = 200
    timestamps = [datetime(2025, 6, 1, 0, 0) + timedelta(minutes=15 * i) for i in range(n)]

    price = 2350.0
    data = {"open": [], "high": [], "low": [], "close": [], "volume": []}
    for _ in range(n):
        o = price
        c = o * (1 + random.gauss(0, 0.0005))
        h = max(o, c) * (1 + abs(random.gauss(0, 0.0002)))
        lo = min(o, c) * (1 - abs(random.gauss(0, 0.0002)))
        v = random.randint(500, 5000)
        data["open"].append(round(o, 2))
        data["high"].append(round(h, 2))
        data["low"].append(round(lo, 2))
        data["close"].append(round(c, 2))
        data["volume"].append(float(v))
        price = c

    return data, timestamps
