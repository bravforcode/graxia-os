"""
Sanity check: Run 500 campaigns on pure random-walk data (no edge).
If DSR passes on noise, the correction is broken.
"""
import numpy as np
import pandas as pd
from datetime import datetime, timedelta

# Monkey-patch load_ohlcv to return random walk data
import paper_engine.price_feed as pf

def _random_walk_ohlcv(symbol, timeframe, n=2000):
    """Generate random walk OHLCV data — no edge, pure noise."""
    rng = np.random.default_rng(hash(symbol + timeframe) % 2**31)
    # Random walk with realistic vol
    returns = rng.normal(0.0001, 0.01, n)  # slight positive drift to match market
    close = 100 * np.exp(np.cumsum(returns))
    high = close * (1 + rng.uniform(0, 0.005, n))
    low = close * (1 - rng.uniform(0, 0.005, n))
    open_ = close * (1 + rng.uniform(-0.002, 0.002, n))
    volume = rng.uniform(1000, 10000, n)

    dates = pd.date_range("2020-01-01", periods=n, freq="D")
    df = pd.DataFrame({
        "open": open_, "high": high, "low": low, "close": close, "volume": volume
    }, index=dates)
    return df

# Save original and monkey-patch
_original_load = pf.load_ohlcv
pf.load_ohlcv = _random_walk_ohlcv

from paper_engine.campaign import generate_campaigns
from paper_engine.engine import run_campaign
from paper_engine.analyzer import deflated_sharpe_ratio

# Generate campaigns (same as real run)
campaigns = generate_campaigns(
    strategies=["tsm", "donchian", "volume_breakout"],
    symbols=["XAUUSD", "EURUSD", "BTCUSD"],
    timeframes=["D1", "H4"],
    param_variations=True,
)

print(f"Running {len(campaigns)} campaigns on RANDOM WALK data...")
results = []
for i, c in enumerate(campaigns):
    r = run_campaign(c)
    m = r.metrics
    sharpe = m.get("sharpe", 0)
    trades = m.get("total_trades", 0)
    results.append({
        "id": c.campaign_id,
        "strategy": c.strategy_id,
        "symbol": c.symbol,
        "tf": c.timeframe,
        "trades": trades,
        "sharpe": sharpe,
    })
    if (i + 1) % 50 == 0:
        print(f"  {i+1}/{len(campaigns)} done")

# Restore original
pf.load_ohlcv = _original_load

# Analyze
sharpe_vals = [r["sharpe"] for r in results if r["trades"] >= 100]
print(f"\nRandom walk results ({len(sharpe_vals)} campaigns with >=100 trades):")
print(f"  Mean Sharpe: {np.mean(sharpe_vals):.3f}")
print(f"  Std Sharpe:  {np.std(sharpe_vals):.3f}")
print(f"  Max Sharpe:  {np.max(sharpe_vals):.3f}")
print(f"  Min Sharpe:  {np.min(sharpe_vals):.3f}")

# Top 10 by Sharpe
top10 = sorted([r for r in results if r["trades"] >= 100], key=lambda x: x["sharpe"], reverse=True)[:10]
print(f"\nTop 10 random-walk campaigns:")
for r in top10:
    sr = r["sharpe"]
    t = r["trades"]
    dsr_r = deflated_sharpe_ratio(sr, len(campaigns), t)
    dsr = 1.0 - dsr_r.probability_alpha
    print(f"  {r['strategy']:18s} {r['symbol']:8s} {r['tf']:4s} T={t:5d} SR={sr:+.3f} DSR={dsr:.4f} passes={dsr_r.passes_threshold}")
