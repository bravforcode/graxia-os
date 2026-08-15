"""Analyze all available assets for diversification potential."""

import pandas as pd
import os
import numpy as np

data_dir = "data"
files = [
    f
    for f in os.listdir(data_dir)
    if f.endswith("_D1.csv")
    and not f.endswith(".bak")
    and "yf" not in f
    and "clean" not in f
    and "deduped" not in f
    and "original" not in f
]

results = []
for f in sorted(files):
    df = pd.read_csv(os.path.join(data_dir, f))
    if "time" in df.columns:
        df["time"] = pd.to_datetime(df["time"])
        df = df.set_index("time")

    asset = f.replace("_D1.csv", "")
    returns = df["close"].pct_change().dropna()

    if len(returns) < 500:
        continue

    annual_vol = returns.std() * np.sqrt(252)
    annual_ret = returns.mean() * 252
    sharpe = annual_ret / annual_vol if annual_vol > 0 else 0

    # Max drawdown
    cum = (1 + returns).cumprod()
    running_max = cum.cummax()
    dd = (cum - running_max) / running_max
    max_dd = dd.min()

    results.append(
        {
            "asset": asset,
            "rows": len(df),
            "date_range": f"{df.index[0].date()} to {df.index[-1].date()}",
            "annual_vol": annual_vol,
            "annual_ret": annual_ret,
            "sharpe": sharpe,
            "max_dd": max_dd,
        }
    )

# Print summary
print("=" * 90)
print(f"{'Asset':<12} {'Rows':<7} {'Sharpe':<8} {'Vol':<8} {'Ret':<8} {'MaxDD':<8} {'Date Range'}")
print("=" * 90)
for r in sorted(results, key=lambda x: x["rows"], reverse=True):
    print(
        f"{r['asset']:<12} {r['rows']:<7} {r['sharpe']:<8.3f} {r['annual_vol']:<8.2%} {r['annual_ret']:<8.2%} {r['max_dd']:<8.2%} {r['date_range']}"
    )

# Correlation matrix
print("\n\n=== CROSS-ASSET CORRELATION MATRIX ===")
all_assets = [r["asset"] for r in results if r["rows"] > 2000]
price_data = {}
for asset in all_assets:
    f = os.path.join(data_dir, f"{asset}_D1.csv")
    if os.path.exists(f):
        df = pd.read_csv(f)
        if "time" in df.columns:
            df["time"] = pd.to_datetime(df["time"])
            df = df.set_index("time")
        price_data[asset] = df["close"]

prices_df = pd.DataFrame(price_data).ffill().dropna()
returns_df = prices_df.pct_change().dropna()
corr = returns_df.corr()

# Print
header = f"{'':>12}"
for a in all_assets:
    header += f"{a[:6]:>8}"
print(header)
for a in all_assets:
    row = f"{a:<12}"
    for b in all_assets:
        row += f"{corr.loc[a, b]:>8.2f}"
    print(row)

# Average correlation per asset
print("\n\n=== AVERAGE CORRELATION WITH OTHERS ===")
for a in all_assets:
    others = [b for b in all_assets if b != a]
    avg_corr = corr.loc[a, others].mean()
    print(f"  {a:<12}: avg_corr = {avg_corr:.3f}")

# Find uncorrelated pairs
print("\n\n=== MOST UNCORRELATED PAIRS ===")
pairs = []
for i, a in enumerate(all_assets):
    for b in all_assets[i + 1 :]:
        pairs.append((a, b, corr.loc[a, b]))
pairs.sort(key=lambda x: abs(x[2]))
for a, b, c in pairs[:10]:
    print(f"  {a:<12} <-> {b:<12}: {c:.3f}")

# Find most diversified portfolio
print("\n\n=== PORTFOLIO DIVERSIFICATION POTENTIAL ===")
# Equal weight portfolio of all assets
equal_weight_returns = returns_df.mean(axis=1)
ew_sharpe = equal_weight_returns.mean() * 252 / (equal_weight_returns.std() * np.sqrt(252))
ew_vol = equal_weight_returns.std() * np.sqrt(252)
ew_ret = equal_weight_returns.mean() * 252
ew_cum = (1 + equal_weight_returns).cumprod()
ew_max_dd = ((ew_cum - ew_cum.cummax()) / ew_cum.cummax()).min()

print(f"Equal-weight across {len(all_assets)} assets:")
print(f"  Sharpe:   {ew_sharpe:.3f}")
print(f"  Vol:      {ew_vol:.2%}")
print(f"  Ret:      {ew_ret:.2%}")
print(f"  MaxDD:    {ew_max_dd:.2%}")
print(f"  Avg corr: {corr.values[np.triu_indices(len(corr), k=1)].mean():.3f}")
