"""
Correct multiple-testing correction: permutation test.
Build null distribution of "best Sharpe from 500 campaigns" by shuffling trade P&L.
"""
import json
import duckdb
import numpy as np

con = duckdb.connect("reports/paper_engine/campaign_results.duckdb", read_only=True)
rows = con.execute("""
    SELECT campaign_id, strategy_id, symbol, timeframe, total_trades, sharpe, trades_json
    FROM campaigns
    WHERE error IS NULL AND total_trades >= 100
    ORDER BY sharpe DESC
""").fetchall()
con.close()

print(f"Campaigns with >=100 trades: {len(rows)}")

# Extract per-trade P&L for each campaign
campaign_pnls = {}
for row in rows:
    cid, strat, sym, tf, trades, sharpe, tj = row
    tlist = json.loads(tj)
    if tlist:
        pnls = np.array([t["net_pnl"] for t in tlist])
        campaign_pnls[cid] = {"pnls": pnls, "sharpe": sharpe, "trades": trades, "strat": strat, "sym": sym, "tf": tf}

# Observed top Sharpe
top_observed = sorted(campaign_pnls.values(), key=lambda x: x["sharpe"], reverse=True)[:10]
print(f"\nObserved top 10:")
for r in top_observed:
    print(f"  {r['strat']:18s} {r['sym']:8s} {r['tf']:4s} T={r['trades']:5d} SR={r['sharpe']:+.3f}")

# Permutation test: FLIP SIGNS of P&L to destroy signal direction
# This preserves the magnitude distribution but breaks any directional edge
n_perms = 2000
rng = np.random.default_rng(42)
max_sharpes = []

print(f"\nRunning {n_perms} permutations (sign-flipping)...")
for perm_i in range(n_perms):
    perm_sharpes = []
    for cid, data in campaign_pnls.items():
        pnls = data["pnls"]
        # Randomly flip signs of each trade's P&L
        signs = rng.choice([-1, 1], size=len(pnls))
        flipped = pnls * signs
        s_std = flipped.std(ddof=1)
        if s_std > 1e-10:
            sr = float(flipped.mean() / s_std * np.sqrt(252))
            perm_sharpes.append(sr)
    if perm_sharpes:
        max_sharpes.append(max(perm_sharpes))
    if (perm_i + 1) % 500 == 0:
        print(f"  {perm_i+1}/{n_perms} done")

max_arr = np.array(max_sharpes)
print(f"\nNull distribution of 'best Sharpe from {len(campaign_pnls)} noise campaigns':")
print(f"  Mean: {max_arr.mean():.3f}")
print(f"  Std:  {max_arr.std():.3f}")
print(f"  95th percentile: {np.percentile(max_arr, 95):.3f}")
print(f"  99th percentile: {np.percentile(max_arr, 99):.3f}")
print(f"  Max:  {max_arr.max():.3f}")

# Compare observed top Sharpe to null
observed_best = top_observed[0]["sharpe"]
p_value = float(np.mean(max_arr >= observed_best))
print(f"\nObserved best Sharpe: {observed_best:.3f}")
print(f"p-value (permutation): {p_value:.4f}")
if p_value < 0.05:
    print("RESULT: Observed best Sharpe is SIGNIFICANTLY higher than expected from noise (p < 0.05)")
else:
    print("RESULT: Observed best Sharpe is NOT significantly different from noise selection (p >= 0.05)")

# How many observed top 10 survive?
print(f"\nSurvival of observed top 10 against null 95th percentile:")
threshold_95 = np.percentile(max_arr, 95)
for r in top_observed:
    survives = r["sharpe"] > threshold_95
    print(f"  {r['strat']:18s} {r['sym']:8s} {r['tf']:4s} SR={r['sharpe']:+.3f} {'PASS' if survives else 'FAIL'} (threshold={threshold_95:.3f})")
