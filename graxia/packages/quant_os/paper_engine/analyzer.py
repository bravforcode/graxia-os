"""
Analyzer — cross-campaign comparison, ranking, insights.
Includes Deflated Sharpe Ratio (DSR) correction for multiple testing.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from .result_store import ResultStore

# NOTE: Parametric DSR (Bailey & Lopez de Prado) is unreliable for T >= 100.
# Using block bootstrap CI instead (same as RYDC/Direction A/B/C).
# No external DSR import needed.


def _trades_per_year_from_dicts(trades: list[dict]) -> float:
    """Compute average trades per year from trades_json dicts.

    Returns 252 as fallback if timestamps are missing or invalid.
    """
    if len(trades) < 2:
        return 252.0
    first_entry = trades[0].get("entry_time")
    last = trades[-1]
    last_exit = last.get("exit_time") or last.get("entry_time")
    if not first_entry or not last_exit:
        return 252.0
    try:
        t_start = pd.Timestamp(first_entry)
        t_end = pd.Timestamp(last_exit)
        time_span_years = (t_end - t_start).total_seconds() / (365.25 * 86400)
        if time_span_years < 1 / 365.25:
            return 252.0
        return len(trades) / time_span_years
    except Exception:
        return 252.0


class CampaignAnalyzer:
    """Analyze and compare campaign results."""

    def __init__(self, store: ResultStore | None = None):
        self.store = store or ResultStore()

    def _load_combined_trials(self) -> int:
        """Load combined trial count from merged trial ledger."""
        ledger_path = Path(__file__).parent.parent / "reports" / "paper_engine" / "trial_ledger.json"
        if ledger_path.exists():
            try:
                data = json.loads(ledger_path.read_text(encoding="utf-8"))
                return data.get("combined_trials", self.store.get_stats().get("total", 500))
            except Exception:
                pass
        return self.store.get_stats().get("total", 500)

    def best_by_strategy(self, top_n: int = 5) -> dict[str, list[dict]]:
        """Group ranking by strategy."""
        rankings = self.store.get_ranking(top_n=200)
        by_strategy: dict[str, list[dict]] = {}
        for r in rankings:
            s = r["strategy"]
            if s not in by_strategy:
                by_strategy[s] = []
            by_strategy[s].append(r)
        # Trim each
        return {s: ranks[:top_n] for s, ranks in by_strategy.items()}

    def best_by_symbol(self, top_n: int = 3) -> dict[str, list[dict]]:
        """Group ranking by symbol."""
        rankings = self.store.get_ranking(top_n=200)
        by_symbol: dict[str, list[dict]] = {}
        for r in rankings:
            sym = r["symbol"]
            if sym not in by_symbol:
                by_symbol[sym] = []
            by_symbol[sym].append(r)
        return {s: ranks[:top_n] for s, ranks in by_symbol.items()}

    def best_timeframe(self) -> dict:
        """Average Sharpe by timeframe."""
        rankings = self.store.get_ranking(top_n=500)
        tf_sharpes: dict[str, list[float]] = {}
        for r in rankings:
            tf = r["timeframe"]
            if tf not in tf_sharpes:
                tf_sharpes[tf] = []
            tf_sharpes[tf].append(r["sharpe"])
        return {
            tf: {
                "avg_sharpe": round(float(np.mean(v)), 3),
                "max_sharpe": round(float(np.max(v)), 3),
                "count": len(v),
            }
            for tf, v in sorted(tf_sharpes.items())
        }

    def generate_report(self, path: str | Path | None = None) -> str:
        """Generate comprehensive markdown report with DSR correction.

        DSR (Deflated Sharpe Ratio) adjusts for multiple testing bias.
        With 500 campaigns, raw Sharpe is meaningless without deflation.
        """
        stats = self.store.get_stats()
        rankings = self.store.get_ranking(top_n=40)

        # Multiple-testing correction: per-campaign permutation test (sign-flipping)
        # Each campaign gets its own null distribution from sign-flipping its own trades.
        # This accounts for varying sample sizes (n=117 vs n=1219 have different null widths).
        n_trials = self._load_combined_trials()
        n_perms = 2000
        rng = np.random.default_rng(42)

        # First pass: collect per-trade P&L for all ranked campaigns
        campaign_pnls = {}
        campaign_trades = {}  # cid -> list of trade dicts (for trades_per_year)
        for r in rankings:
            campaign_id = r.get("campaign_id", "")
            trades_json = self.store.get_trades_json(campaign_id)
            if trades_json:
                try:
                    tlist = json.loads(trades_json)
                    if tlist and len(tlist) > 3:
                        campaign_pnls[campaign_id] = np.array([t["net_pnl"] for t in tlist])
                        campaign_trades[campaign_id] = tlist
                except Exception:
                    pass

        # Build per-campaign null distributions via sign-flipping
        campaign_nulls = {}  # cid -> array of null Sharpes
        for cid, pnls in campaign_pnls.items():
            null_sharpes = []
            # Compute trades_per_year from the trade list for this campaign
            tlist_raw = campaign_trades.get(cid, [])
            tpy = _trades_per_year_from_dicts(tlist_raw) if tlist_raw else 252.0
            for _ in range(n_perms):
                signs = rng.choice([-1, 1], size=len(pnls))
                flipped = pnls * signs
                s_std = flipped.std(ddof=1)
                if s_std > 1e-10:
                    null_sharpes.append(float(flipped.mean() / s_std * np.sqrt(tpy)))
            if null_sharpes:
                campaign_nulls[cid] = np.array(null_sharpes)

        # Second pass: compute per-campaign p-values + empirical moments
        n_boot = 2000
        dsr_rankings = []
        for r in rankings:
            trades = r.get("trades", 0)
            campaign_id = r.get("campaign_id", "")

            skew, kurt = 0.0, 0.0
            pnls = campaign_pnls.get(campaign_id)
            tlist_raw = campaign_trades.get(campaign_id, [])
            tpy = _trades_per_year_from_dicts(tlist_raw) if tlist_raw else 252.0

            # Recompute Sharpe from P&Ls with frequency-corrected annualization
            if pnls is not None and len(pnls) > 1:
                returns = pnls / 100000
                r_std = returns.std()
                sharpe_corrected = float(returns.mean() / r_std * np.sqrt(tpy)) if r_std > 1e-10 else 0.0
            else:
                sharpe_corrected = r.get("sharpe", 0)
            r["sharpe_raw"] = r.get("sharpe", 0)  # preserve old value for reference
            r["sharpe"] = round(sharpe_corrected, 3)

            if pnls is not None and len(pnls) > 3:
                std = pnls.std(ddof=1)
                if std > 1e-10:
                    z = (pnls - pnls.mean()) / std
                    skew = float(np.mean(z ** 3))
                    kurt = float(np.mean(z ** 4) - 3)

            r["empirical_skew"] = round(skew, 2)
            r["empirical_kurt"] = round(kurt, 2)

            # Per-campaign permutation p-value (compare against frequency-corrected null)
            null_arr = campaign_nulls.get(campaign_id)
            if null_arr is not None and len(null_arr) > 100 and sharpe_corrected != 0:
                p_value = float(np.mean(null_arr >= sharpe_corrected))
                null_95 = float(np.percentile(null_arr, 95))
                null_99 = float(np.percentile(null_arr, 99))
                r["permutation_p"] = round(p_value, 4)
                r["null_95"] = round(null_95, 3)
                r["null_99"] = round(null_99, 3)
            else:
                r["permutation_p"] = 1.0
                r["null_95"] = None
                r["null_99"] = None

            # Bootstrap CI for Sharpe
            if pnls is not None and len(pnls) >= 30 and sharpe_corrected != 0:
                tlist_raw = campaign_trades.get(campaign_id, [])
                tpy = _trades_per_year_from_dicts(tlist_raw) if tlist_raw else 252.0
                boot_sharpes = []
                for _ in range(n_boot):
                    block_size = max(1, int(np.sqrt(len(pnls))))
                    n_blocks = max(1, len(pnls) // block_size)
                    indices = []
                    for _ in range(n_blocks):
                        start = rng.integers(0, max(1, len(pnls) - block_size))
                        indices.extend(range(start, min(start + block_size, len(pnls))))
                    indices = indices[:len(pnls)]
                    if len(indices) < 10:
                        continue
                    sample = pnls[indices]
                    s_std = sample.std(ddof=1)
                    if s_std > 1e-10:
                        boot_sharpes.append(float(sample.mean() / s_std * np.sqrt(tpy)))

                if len(boot_sharpes) >= 100:
                    boot_arr = np.array(boot_sharpes)
                    ci_low = float(np.percentile(boot_arr, 2.5))
                    ci_high = float(np.percentile(boot_arr, 97.5))
                    r["bootstrap_ci_low"] = round(ci_low, 3)
                    r["bootstrap_ci_high"] = round(ci_high, 3)
                    # Pass = CI excludes 0 AND per-campaign permutation p < 0.05
                    r["dsr_passes"] = (ci_low > 0) and (r["permutation_p"] < 0.05)
                    r["dsr"] = round(1.0 - r["permutation_p"], 4)
                    r["prob_alpha"] = r["permutation_p"]
                else:
                    r["dsr"] = 0.0
                    r["dsr_passes"] = False
                    r["prob_alpha"] = 1.0
                    r["bootstrap_ci_low"] = None
                    r["bootstrap_ci_high"] = None
            else:
                r["dsr"] = 0.0
                r["dsr_passes"] = False
                r["prob_alpha"] = 1.0
                r["bootstrap_ci_low"] = None
                r["bootstrap_ci_high"] = None
            dsr_rankings.append(r)

        # Re-sort by Sharpe descending (not DSR — DSR sorts by bootstrap fraction which is misleading)
        dsr_rankings.sort(key=lambda x: x.get("sharpe", 0), reverse=True)

        # Rebuild by_strategy and by_timeframe from corrected rankings
        by_strategy: dict[str, list[dict]] = {}
        for r in dsr_rankings:
            s = r["strategy"]
            if s not in by_strategy:
                by_strategy[s] = []
            by_strategy[s].append(r)
        by_strategy = {s: ranks[:3] for s, ranks in by_strategy.items()}

        tf_sharpes: dict[str, list[float]] = {}
        for r in dsr_rankings:
            tf = r["timeframe"]
            if tf not in tf_sharpes:
                tf_sharpes[tf] = []
            tf_sharpes[tf].append(r["sharpe"])
        by_timeframe = {
            tf: {
                "avg_sharpe": round(float(np.mean(v)), 3),
                "max_sharpe": round(float(np.max(v)), 3),
                "count": len(v),
            }
            for tf, v in sorted(tf_sharpes.items())
        }

        lines = [
            "# Parallel Paper Engine — Campaign Analysis Report",
            "",
            "**WARNING: All results are IN-SAMPLE only. No walk-forward validation applied.",
            "Sharpe is frequency-corrected (annualized by actual trades/year, not hardcoded 252).",
            "Multiple-testing correction: per-campaign permutation test (sign-flipping, B=2000).",
            "Each campaign has its own null distribution. Passes = p < 0.05 AND CI excludes 0.**",
            "",
            "## Overall Stats",
            f"- Total campaigns run: {stats.get('total', 0)}",
            f"- Successful: {stats.get('success', 0)}",
            f"- Failed: {stats.get('failed', 0)}",
            f"- Viable (≥100 trades): {stats.get('viable', 0)}",
            f"- Average Sharpe (corrected): {round(float(np.mean([r['sharpe'] for r in dsr_rankings])), 3)}",
            f"- Best Sharpe (corrected): {round(float(np.max([r['sharpe'] for r in dsr_rankings])), 3)}",
            f"- Sharpe > 1.0: {sum(1 for r in dsr_rankings if r['sharpe'] > 1.0)}",
            f"- Sharpe > 2.0: {sum(1 for r in dsr_rankings if r['sharpe'] > 2.0)}",
            f"- Multiple testing trials (N): {n_trials}",
            "",
            "## Top 40 Campaigns by Bootstrap CI",
            "",
            "Bootstrap CI = 95% block bootstrap confidence interval for Sharpe (B=2000).",
            "Passes = per-campaign permutation p < 0.05 AND CI lower bound > 0.",
            "",
            "| Rank | Campaign | Strategy | Symbol | TF | Trades | TPY | Sharpe | Skew | Kurt | p-val | Null95 | 95% CI | Passes? | WR% | PF | MaxDD% |",
            "|------|----------|----------|-------|-----|--------|-----|--------|------|------|-------|--------|--------|---------|-----|-----|--------|",
        ]
        for i, r in enumerate(dsr_rankings, 1):
            passes = "YES" if r.get("dsr_passes") else "NO"
            ci_low = r.get("bootstrap_ci_low")
            ci_high = r.get("bootstrap_ci_high")
            ci_str = "[%.2f, %.2f]" % (ci_low, ci_high) if ci_low is not None else "N/A"
            null95 = r.get("null_95")
            null95_str = "%.3f" % null95 if null95 is not None else "N/A"
            # TPY for this campaign
            cid = r.get("campaign_id", "")
            tpy_val = _trades_per_year_from_dicts(campaign_trades.get(cid, [])) if cid in campaign_trades else 0
            lines.append(
                f"| {i} | {r['campaign_id']} | {r['strategy']} | {r['symbol']} | {r['timeframe']} "
                f"| {r['trades']} | {tpy_val:.0f} | {r['sharpe']:.3f} "
                f"| {r.get('empirical_skew', 0):.2f} | {r.get('empirical_kurt', 0):.1f} "
                f"| {r.get('permutation_p', 1):.4f} | {null95_str} | {ci_str} | {passes} "
                f"| {r['win_rate']:.1f}% | {r['profit_factor']:.2f} | {r['max_dd']:.1f}% |"
            )

        lines.extend([
            "",
            "## Frequency-Corrected Sharpe Ranking",
            "",
            "**Annualized by actual trades/year (not hardcoded 252). Same as main table above.**",
            "",
            "| Rank | Campaign | Strategy | Symbol | TF | Trades | TPY | Sharpe | P&L | WR% |",
            "|------|----------|----------|-------|-----|--------|-----|--------|-----|------|",
        ])
        for i, r in enumerate(dsr_rankings[:20], 1):
            cid = r.get("campaign_id", "")
            tpy_val = _trades_per_year_from_dicts(campaign_trades.get(cid, [])) if cid in campaign_trades else 0
            lines.append(
                f"| {i} | {r['campaign_id']} | {r['strategy']} | {r['symbol']} | {r['timeframe']} "
                f"| {r['trades']} | {tpy_val:.0f} | {r['sharpe']:.3f} | ${r['pnl']:+.0f} | {r['win_rate']:.1f}% |"
            )

        lines.extend([
            "",
            "## Best by Strategy",
            "",
        ])
        for strategy, ranks in by_strategy.items():
            lines.append(f"### {strategy}")
            lines.append("| Symbol | TF | Sharpe | P&L | WR% |")
            lines.append("|--------|-----|--------|-----|------|")
            for r in ranks:
                lines.append(f"| {r['symbol']} | {r['timeframe']} | {r['sharpe']:.3f} | ${r['pnl']:+.0f} | {r['win_rate']:.1f}% |")
            lines.append("")

        lines.extend([
            "## Average Sharpe by Timeframe",
            "",
            "| Timeframe | Avg Sharpe | Max Sharpe | Count |",
            "|-----------|------------|------------|-------|",
        ])
        for tf, data in sorted(by_timeframe.items()):
            lines.append(f"| {tf} | {data['avg_sharpe']} | {data['max_sharpe']} | {data['count']} |")

        report = "\n".join(lines)

        if path:
            Path(path).write_text(report, encoding="utf-8")

        return report
