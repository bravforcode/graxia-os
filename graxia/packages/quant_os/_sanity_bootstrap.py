"""Sanity check: Bootstrap CI on random walk data should FAIL."""
import numpy as np
import importlib.util as ilu
from pathlib import Path

# Monkey-patch load_ohlcv
import paper_engine.price_feed as pf
def _random_walk_ohlcv(symbol, timeframe, n=2000):
    rng = np.random.default_rng(hash(symbol + timeframe) % 2**31)
    returns = rng.normal(0.0001, 0.01, n)
    close = 100 * np.exp(np.cumsum(returns))
    high = close * (1 + rng.uniform(0, 0.005, n))
    low = close * (1 - rng.uniform(0, 0.005, n))
    open_ = close * (1 + rng.uniform(-0.002, 0.002, n))
    volume = rng.uniform(1000, 10000, n)
    import pandas as pd
    dates = pd.date_range("2020-01-01", periods=n, freq="D")
    return pd.DataFrame({"open": open_, "high": high, "low": low, "close": close, "volume": volume}, index=dates)

_original = pf.load_ohlcv
pf.load_ohlcv = _random_walk_ohlcv

from paper_engine.campaign import generate_campaigns
from paper_engine.engine import run_campaign

campaigns = generate_campaigns(
    strategies=["tsm", "donchian", "volume_breakout"],
    symbols=["XAUUSD", "EURUSD", "BTCUSD"],
    timeframes=["D1", "H4"],
    param_variations=True,
)

print(f"Running {len(campaigns)} campaigns on RANDOM WALK...")
results = []
for c in campaigns:
    r = run_campaign(c)
    m = r.metrics
    if m.get("total_trades", 0) >= 100:
        pnls = np.array([t.net_pnl for t in r.trades])
        results.append({"id": c.campaign_id, "strat": c.strategy_id, "sym": c.symbol,
                        "tf": c.timeframe, "trades": m["total_trades"], "sharpe": m["sharpe"], "pnls": pnls})

pf.load_ohlcv = _original

# Bootstrap CI for top 10
rng = np.random.default_rng(42)
n_boot = 2000
top = sorted(results, key=lambda x: x["sharpe"], reverse=True)[:10]

print(f"\nRandom walk top 10 (bootstrap CI):")
print(f"{'Strategy':18s} {'Symbol':8s} {'TF':4s} {'T':5s} {'Sharpe':8s} {'95% CI':20s} {'Passes?':8s}")
print("-" * 80)
for r in top:
    pnls = r["pnls"]
    boot_sharpes = []
    for _ in range(n_boot):
        block_size = max(1, int(np.sqrt(len(pnls))))
        n_blocks = max(1, len(pnls) // block_size)
        indices = []
        for _ in range(n_blocks):
            start = rng.integers(0, max(1, len(pnls) - block_size))
            indices.extend(range(start, min(start + block_size, len(pnls))))
        indices = indices[:len(pnls)]
        sample = pnls[indices]
        s_std = sample.std(ddof=1)
        if s_std > 1e-10:
            boot_sharpes.append(float(sample.mean() / s_std * np.sqrt(252)))

    boot_arr = np.array(boot_sharpes)
    ci_low = float(np.percentile(boot_arr, 2.5))
    ci_high = float(np.percentile(boot_arr, 97.5))
    passes = ci_low > 0
    print(f"{r['strat']:18s} {r['sym']:8s} {r['tf']:4s} {r['trades']:5d} {r['sharpe']:+8.3f} [{ci_low:+.2f}, {ci_high:+.2f}]{'':5s} {'YES' if passes else 'NO'}")
