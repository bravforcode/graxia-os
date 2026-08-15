"""Check correlation between top-40 campaigns — especially donchian cluster.

If Donchian breakout strategies on different symbols/timeframes all capture
the same underlying trend, they're not independent evidence. This script
computes correlation matrix and effective sample size.
"""
import json
import os
import sys
from pathlib import Path

_script_dir = Path(__file__).resolve().parent
_project_root = _script_dir.parent
os.chdir(_project_root)
sys.path.insert(0, str(_project_root))

import duckdb
import numpy as np
import pandas as pd

REPORTS = _project_root / "reports" / "paper_engine"


def main():
    # 1. Load top 40 campaigns
    con = duckdb.connect(str(REPORTS / "campaign_results.duckdb"), read_only=True)
    rows = con.execute("""
        SELECT campaign_id, strategy_id, symbol, timeframe, sharpe, total_trades, trades_json
        FROM campaigns
        WHERE error IS NULL AND total_trades >= 100 AND sharpe IS NOT NULL
        ORDER BY sharpe DESC
        LIMIT 40
    """).fetchall()
    con.close()

    print(f"Loaded {len(rows)} campaigns")

    # 2. Build return series for each campaign
    campaigns = []
    for cid, strategy, symbol, tf, sharpe, trades, trades_json in rows:
        trades_data = json.loads(trades_json) if trades_json else []
        if not trades_data:
            continue

        # Build daily P&L series
        daily_pnl = {}
        for t in trades_data:
            exit_time = t.get("exit_time", "")
            if exit_time:
                day = exit_time[:10]  # YYYY-MM-DD
                daily_pnl[day] = daily_pnl.get(day, 0) + t.get("net_pnl", 0)

        campaigns.append({
            "campaign_id": cid,
            "strategy": strategy,
            "symbol": symbol,
            "timeframe": tf,
            "sharpe": sharpe,
            "daily_pnl": daily_pnl,
        })

    # 3. Create DataFrame of daily returns
    all_days = sorted(set(d for c in campaigns for d in c["daily_pnl"]))
    return_df = pd.DataFrame(0.0, index=all_days, columns=[c["campaign_id"] for c in campaigns])

    for c in campaigns:
        for day, pnl in c["daily_pnl"].items():
            return_df.loc[day, c["campaign_id"]] = pnl

    # 4. Compute correlation matrix
    corr_matrix = return_df.corr()

    # 5. Analyze by strategy cluster
    print("\n=== CORRELATION ANALYSIS ===\n")

    # Group by strategy
    strategies = {}
    for c in campaigns:
        s = c["strategy"]
        if s not in strategies:
            strategies[s] = []
        strategies[s].append(c["campaign_id"])

    print("Strategy clusters:")
    for s, ids in strategies.items():
        print(f"  {s}: {len(ids)} campaigns")

    # Compute average correlation within each strategy cluster
    print("\n=== WITHIN-CLUSTER CORRELATION ===\n")
    for s, ids in strategies.items():
        if len(ids) < 2:
            continue
        cluster_corr = []
        for i in range(len(ids)):
            for j in range(i+1, len(ids)):
                if ids[i] in corr_matrix.index and ids[j] in corr_matrix.columns:
                    cluster_corr.append(corr_matrix.loc[ids[i], ids[j]])
        if cluster_corr:
            avg_corr = np.mean(cluster_corr)
            print(f"  {s}: avg correlation = {avg_corr:.3f} (n={len(cluster_corr)} pairs)")

    # 6. Overall correlation stats
    print("\n=== OVERALL CORRELATION STATS ===\n")
    # Get upper triangle (excluding diagonal)
    mask = np.triu(np.ones_like(corr_matrix, dtype=bool), k=1)
    upper_vals = corr_matrix.values[mask]
    upper_vals = upper_vals[~np.isnan(upper_vals)]

    print(f"  Mean correlation: {np.mean(upper_vals):.3f}")
    print(f"  Median correlation: {np.median(upper_vals):.3f}")
    print(f"  Max correlation: {np.max(upper_vals):.3f}")
    print(f"  Pairs with corr > 0.5: {np.sum(upper_vals > 0.5)}/{len(upper_vals)}")
    print(f"  Pairs with corr > 0.7: {np.sum(upper_vals > 0.7)}/{len(upper_vals)}")

    # 7. Effective sample size
    # Formula: N_eff = N * (1 - avg_corr) / (1 + avg_corr)
    # Where N = number of independent observations (campaigns)
    n = len(campaigns)
    avg_corr = np.mean(upper_vals)
    n_eff = n * (1 - avg_corr) / (1 + avg_corr)

    print(f"\n=== EFFECTIVE SAMPLE SIZE ===\n")
    print(f"  Nominal N: {n}")
    print(f"  Average pairwise correlation: {avg_corr:.3f}")
    print(f"  Effective N (corrected): {n_eff:.1f}")
    print(f"  Reduction: {(1 - n_eff/n)*100:.1f}%")

    # 8. Donchian-specific analysis
    donchian_ids = [c["campaign_id"] for c in campaigns if c["strategy"] == "donchian"]
    if len(donchian_ids) > 1:
        donchian_corr = []
        for i in range(len(donchian_ids)):
            for j in range(i+1, len(donchian_ids)):
                if donchian_ids[i] in corr_matrix.index and donchian_ids[j] in corr_matrix.columns:
                    donchian_corr.append(corr_matrix.loc[donchian_ids[i], donchian_ids[j]])

        print(f"\n=== DONCHIAN CLUSTER ANALYSIS ===\n")
        print(f"  Donchian campaigns: {len(donchian_ids)}")
        print(f"  Average intra-donchian correlation: {np.mean(donchian_corr):.3f}")
        print(f"  Max intra-donchian correlation: {np.max(donchian_corr):.3f}")

        # Effective N for donchian only
        n_donch = len(donchian_ids)
        avg_donch_corr = np.mean(donchian_corr)
        n_eff_donch = n_donch * (1 - avg_donch_corr) / (1 + avg_donch_corr)
        print(f"  Effective N for donchian: {n_eff_donch:.1f} (of {n_donch})")

        # Find most correlated pairs
        print(f"\n  Top 10 most correlated donchian pairs:")
        pairs = []
        for i in range(len(donchian_ids)):
            for j in range(i+1, len(donchian_ids)):
                if donchian_ids[i] in corr_matrix.index and donchian_ids[j] in corr_matrix.columns:
                    pairs.append((donchian_ids[i], donchian_ids[j], corr_matrix.loc[donchian_ids[i], donchian_ids[j]]))
        pairs.sort(key=lambda x: x[2], reverse=True)
        for a, b, corr in pairs[:10]:
            ca = next(c for c in campaigns if c["campaign_id"] == a)
            cb = next(c for c in campaigns if c["campaign_id"] == b)
            print(f"    {a} ({ca['symbol']} {ca['timeframe']}) <-> {b} ({cb['symbol']} {cb['timeframe']}): {corr:.3f}")

    # 9. Cross-strategy correlation
    print(f"\n=== CROSS-STRATEGY CORRELATION ===\n")
    for s1 in strategies:
        for s2 in strategies:
            if s1 >= s2:
                continue
            cross_corr = []
            for id1 in strategies[s1]:
                for id2 in strategies[s2]:
                    if id1 in corr_matrix.index and id2 in corr_matrix.columns:
                        cross_corr.append(corr_matrix.loc[id1, id2])
            if cross_corr:
                print(f"  {s1} <-> {s2}: avg {np.mean(cross_corr):.3f}")

    # 10. Summary
    print(f"\n=== SUMMARY ===\n")
    if avg_corr > 0.6:
        print("  WARNING: High average correlation — campaigns are NOT independent evidence")
        print(f"  Effective sample size ({n_eff:.0f}) is much smaller than nominal ({n})")
    elif avg_corr > 0.4:
        print("  MODERATE: Some correlation — effective sample size reduced")
        print(f"  Effective N: {n_eff:.0f} vs nominal {n}")
    else:
        print("  OK: Low correlation — campaigns provide mostly independent evidence")
        print(f"  Effective N: {n_eff:.0f} vs nominal {n}")

    # Save correlation matrix
    corr_path = REPORTS / "correlation_matrix.csv"
    corr_matrix.to_csv(corr_path)
    print(f"\n  Correlation matrix saved to {corr_path}")


if __name__ == "__main__":
    main()
