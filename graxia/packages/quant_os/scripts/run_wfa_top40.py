"""Run walk-forward validation on top 40 campaigns and generate OOS comparison report."""
import json
import os
import sys
import time
from pathlib import Path

# Ensure we're in the right directory and module path is set
_script_dir = Path(__file__).resolve().parent
_project_root = _script_dir.parent
os.chdir(_project_root)
sys.path.insert(0, str(_project_root))

import duckdb

from paper_engine.campaign import CampaignConfig, get_spread_bps
from paper_engine.engine import run_campaign_wfa

REPORTS = _project_root / "reports" / "paper_engine"


def main():
    # 1. Read top 40 campaigns
    con = duckdb.connect(str(REPORTS / "campaign_results.duckdb"), read_only=True)
    rows = con.execute("""
        SELECT campaign_id, strategy_id, symbol, timeframe, sharpe, total_trades, params_json
        FROM campaigns
        WHERE error IS NULL AND total_trades >= 100 AND sharpe IS NOT NULL
        ORDER BY sharpe DESC
        LIMIT 40
    """).fetchall()
    con.close()

    print(f"Running WFA on {len(rows)} campaigns (5 folds each)...")

    results = []
    t0 = time.time()
    for idx, (cid, strategy, symbol, tf, is_sharpe, trades, params_json) in enumerate(rows):
        print(f"  [{idx+1}/{len(rows)}] {cid} {strategy} {symbol} {tf} (IS Sharpe={is_sharpe:.3f})...")
        config = CampaignConfig(
            campaign_id=cid,
            strategy_id=strategy,
            symbol=symbol,
            timeframe=tf,
            spread_bps=get_spread_bps(symbol),  # real measured spread
            params=json.loads(params_json) if params_json else {},
        )
        try:
            wfa = run_campaign_wfa(config, n_splits=5, embargo_bars=12)
        except Exception as e:
            wfa = {"campaign_id": cid, "error": str(e)}
            print(f"    ERROR: {e}")

        oos_metrics = wfa.get("oos_metrics", {})
        oos_sharpe = oos_metrics.get("sharpe", 0)
        degradation = (1 - oos_sharpe / is_sharpe) * 100 if is_sharpe > 0 else 0

        results.append({
            "campaign_id": cid,
            "strategy": strategy,
            "symbol": symbol,
            "timeframe": tf,
            "is_sharpe": round(is_sharpe, 3),
            "oos_sharpe": round(oos_sharpe, 3),
            "oos_trades": oos_metrics.get("total_trades", 0),
            "oos_pnl": oos_metrics.get("total_pnl", 0),
            "oos_win_rate": oos_metrics.get("win_rate_pct", 0),
            "oos_permutation_p": oos_metrics.get("permutation_p", 1.0),
            "oos_dsr": oos_metrics.get("dsr", 0),
            "degradation_pct": round(degradation, 1),
            "wfa_folds_used": wfa.get("wfa_folds_used", 0),
            "error": wfa.get("error"),
        })
        print(f"    OOS Sharpe={oos_sharpe:.3f}, Degradation={degradation:.1f}%")

    elapsed = time.time() - t0
    print(f"\nDone in {elapsed:.0f}s ({elapsed/len(rows):.1f}s per campaign)")

    # 2. Summary stats
    valid = [r for r in results if r.get("oos_sharpe") is not None and not r.get("error")]
    oos_gt_1 = sum(1 for r in valid if r["oos_sharpe"] > 1.0)
    oos_gt_0 = sum(1 for r in valid if r["oos_sharpe"] > 0)
    avg_oos = sum(r["oos_sharpe"] for r in valid) / len(valid) if valid else 0
    avg_degradation = sum(r["degradation_pct"] for r in valid) / len(valid) if valid else 0
    worst = min(valid, key=lambda r: r["oos_sharpe"]) if valid else None

    # 3. Write report
    lines = [
        "# Walk-Forward Validation Report — Top 40 Campaigns",
        "",
        f"**Date:** {time.strftime('%Y-%m-%d %H:%M')}",
        f"**Campaigns tested:** {len(rows)}",
        f"**WFA config:** 5 folds, 12-bar embargo, 70/30 train/test split",
        f"**Spread cost:** Real measured bps from cost_calibration.json",
        f"**Runtime:** {elapsed:.0f}s",
        "",
        "## Summary",
        "",
        f"- OOS Sharpe > 1.0: **{oos_gt_1}/{len(valid)}** ({oos_gt_1/len(valid)*100:.0f}%)" if valid else "- No valid results",
        f"- OOS Sharpe > 0.0: **{oos_gt_0}/{len(valid)}** ({oos_gt_0/len(valid)*100:.0f}%)" if valid else "",
        f"- Average OOS Sharpe: **{avg_oos:.3f}**" if valid else "",
        f"- Average degradation from IS: **{avg_degradation:.1f}%**" if valid else "",
        f"- Worst OOS: {worst['campaign_id']} ({worst['strategy']} {worst['symbol']} {worst['timeframe']}) OOS={worst['oos_sharpe']:.3f}" if worst else "",
        "",
        "## Detailed Results",
        "",
        "| Rank | Campaign | Strategy | Symbol | TF | IS Sharpe | OOS Sharpe | OOS Trades | OOS P&L | Degradation | Passes? |",
        "|------|----------|----------|-------|-----|-----------|------------|------------|---------|-------------|---------|",
    ]

    for i, r in enumerate(sorted(results, key=lambda x: x.get("oos_sharpe", 0), reverse=True), 1):
        passes = "YES" if r.get("oos_sharpe", 0) > 0 and r.get("oos_permutation_p", 1) < 0.05 else "NO"
        error = "ERR" if r.get("error") else ""
        lines.append(
            f"| {i} | {r['campaign_id']} | {r['strategy']} | {r['symbol']} | {r['timeframe']} "
            f"| {r['is_sharpe']:.3f} | {r.get('oos_sharpe', 0):.3f} | {r.get('oos_trades', 0)} "
            f"| ${r.get('oos_pnl', 0):+,.0f} | {r.get('degradation_pct', 0):.1f}% | {passes} {error} |"
        )

    report = "\n".join(lines)
    report_path = REPORTS / "wfa_report.md"
    report_path.write_text(report, encoding="utf-8")
    print(f"\nReport written to {report_path}")

    # Also save raw results as JSON
    json_path = REPORTS / "wfa_results.json"
    json_path.write_text(json.dumps(results, indent=2, default=str), encoding="utf-8")


if __name__ == "__main__":
    main()
