"""Permutation DSR on BTCUSD H1 donchian candidate with cumulative N derived
from the canonical single source (validation/n_trials.py).

This is step 3 from the plan: check if the candidate passes the same
>0.95 DSR threshold used in RYDC.

STATUS (2026-07-30): this script and its output (reports/paper_engine/
candidate_dsr_result.json) are UNGOVERNED. Never committed to git, never
entered into research/hypothesis_registry.json or any trial_ledger*.json.
N is NOT used in the DSR pass/fail computation itself (decorative only),
so the output verdict is unaffected by N. The DSR=1.0/PASSES=YES result
already on disk is NOT a registered trial verdict; see
reports/paper_engine/candidate_dsr_result.INVALID.md before using it for
anything.

Reconciliation (2026-08-03, Stream C of audit-reconciliation spec):
N is imported from validation/n_trials.py::get_reconciled_n_trials()
(single source of truth). The former hardcoded N literal was removed;
do not reintroduce hardcoded N literals here.
"""

import json
import os
import sys
from pathlib import Path

_script_dir = Path(__file__).resolve().parent
_project_root = _script_dir.parent
os.chdir(_project_root)
sys.path.insert(0, str(_project_root))

import duckdb  # noqa: E402
import numpy as np  # noqa: E402

from paper_engine.campaign import CampaignConfig, get_spread_bps  # noqa: E402
from paper_engine.engine import _permutation_dsr, _trades_per_year, run_campaign  # noqa: E402
from validation.n_trials import get_reconciled_n_trials  # noqa: E402

REPORTS = _project_root / "reports" / "paper_engine"
N_TRIALS = get_reconciled_n_trials()  # single source of truth (validation/n_trials.py)


def main():
    print("=== Permutation DSR on BTCUSD H1 Donchian ===\n")

    # 1. Load candidate from DuckDB
    con = duckdb.connect(str(REPORTS / "campaign_results.duckdb"), read_only=True)
    rows = con.execute("""
        SELECT campaign_id, strategy_id, symbol, timeframe, sharpe, total_trades, trades_json
        FROM campaigns
        WHERE symbol = 'BTCUSD' AND timeframe = 'H1' AND strategy_id = 'donchian'
          AND error IS NULL AND total_trades >= 100
        ORDER BY sharpe DESC
        LIMIT 1
    """).fetchall()
    con.close()

    if not rows:
        print("ERROR: No BTCUSD H1 donchian campaign found")
        return

    cid, strategy, symbol, tf, is_sharpe, trades_count, trades_json = rows[0]
    print(f"Campaign: {cid}")
    print(f"Strategy: {strategy}")
    print(f"Symbol: {symbol}")
    print(f"Timeframe: {tf}")
    print(f"IS Sharpe: {is_sharpe:.3f}")
    print(f"Total trades: {trades_count}")
    print()

    # 2. Re-run with real spread costs
    config = CampaignConfig(
        campaign_id=cid,
        strategy_id=strategy,
        symbol=symbol,
        timeframe=tf,
        spread_bps=get_spread_bps(symbol),
        params={"period": 20, "vol_filter": True},  # default donchian params
    )

    print("Re-running with real spread costs...")
    result = run_campaign(config)
    if result.error:
        print(f"ERROR: {result.error}")
        return

    trades = result.trades
    print(f"Trades generated: {len(trades)}")
    print()

    # 3. Compute metrics
    pnls = np.array([t.net_pnl for t in trades])
    returns = pnls / 100000
    tpy = _trades_per_year(trades)
    sharpe = float(np.mean(returns) / np.std(returns) * np.sqrt(tpy)) if np.std(returns) > 1e-10 else 0.0

    print("=== Metrics (with real spread) ===")
    print(f"  Sharpe: {sharpe:.4f}")
    print(f"  TPY: {tpy:.1f}")
    print(f"  Total P&L: ${np.sum(pnls):,.2f}")
    print(f"  Win rate: {np.mean(pnls > 0)*100:.1f}%")
    print()

    # 4. Permutation DSR (per-campaign, B=2000)
    print("Running permutation DSR (B=2000)...")
    dsr_result = _permutation_dsr(trades, n_perms=2000, seed=42)

    print("\n=== Permutation DSR Results ===")
    print(f"  DSR: {dsr_result['dsr']:.4f}")
    print(f"  Permutation p-value: {dsr_result['permutation_p']:.4f}")
    print(f"  Null 95th percentile: {dsr_result['null_95']:.3f}")
    print(f"  Null 99th percentile: {dsr_result['null_99']:.3f}")
    print()

    # 5. Check threshold
    threshold = 0.95
    passes = dsr_result["dsr"] > threshold
    print("=== Decision ===")
    print(f"  DSR threshold: {threshold}")
    print(f"  Candidate DSR: {dsr_result['dsr']:.4f}")
    print(f"  PASSES: {'YES' if passes else 'NO'}")
    print()

    # 6. Context: N derived from canonical source
    print("=== Cumulative Context ===")
    print(f"  Total trials in program (N): {N_TRIALS}")
    print("  Multiple testing correction applied via permutation test")
    print("  DSR = 1 - p_value (probability this is chance)")
    print()

    if passes:
        print("=== CANDIDATE SURVIVES STEP 3 ===")
        print("  Ready for sacred holdout consideration")
    else:
        print("=== CANDIDATE REJECTED AT STEP 3 ===")
        print("  DSR below threshold - likely overfitting or lucky streak")

    # 7. Save results
    output = {
        "campaign_id": cid,
        "strategy": strategy,
        "symbol": symbol,
        "timeframe": tf,
        "spread_bps": get_spread_bps(symbol),
        "is_sharpe": round(is_sharpe, 4),
        "oos_sharpe_with_spread": round(sharpe, 4),
        "total_trades": len(trades),
        "tpy": round(tpy, 1),
        "total_pnl": round(float(np.sum(pnls)), 2),
        "win_rate_pct": round(float(np.mean(pnls > 0) * 100), 1),
        "dsr": dsr_result["dsr"],
        "permutation_p": dsr_result["permutation_p"],
        "null_95": dsr_result["null_95"],
        "null_99": dsr_result["null_99"],
        "threshold": threshold,
        "passes": passes,
        "n_trials_cumulative": N_TRIALS,
    }

    output_path = REPORTS / "candidate_dsr_result.json"
    output_path.write_text(json.dumps(output, indent=2), encoding="utf-8")
    print(f"\nResults saved to {output_path}")


if __name__ == "__main__":
    main()
