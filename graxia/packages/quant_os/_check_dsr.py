"""Sanity check: empirical skew/kurtosis from trades_json vs DSR default."""
import json
import duckdb
import numpy as np
import importlib.util as _ilu
from pathlib import Path as _Path
_dsr_path = _Path(__file__).resolve().parent / "validation" / "deflated_sharpe.py"
_spec = _ilu.spec_from_file_location("_dsr_mod", str(_dsr_path))
_dsr_mod = _ilu.module_from_spec(_spec)
_spec.loader.exec_module(_dsr_mod)
deflated_sharpe_ratio = _dsr_mod.deflated_sharpe_ratio

con = duckdb.connect("reports/paper_engine/campaign_results.duckdb", read_only=True)
rows = con.execute("""
    SELECT campaign_id, strategy_id, symbol, timeframe, total_trades, sharpe, trades_json
    FROM campaigns
    WHERE error IS NULL AND total_trades >= 100
    ORDER BY sharpe DESC
    LIMIT 10
""").fetchall()
con.close()

print("=" * 120)
print("%-12s %-18s %-8s %-4s %6s %8s %8s %8s %8s %8s %8s" % (
    "Campaign", "Strategy", "Symbol", "TF", "Trades", "Sharpe",
    "Skew", "Kurt", "DSR(def)", "DSR(emp)", "DSR_boot"))
print("=" * 120)

for row in rows:
    cid, strat, sym, tf, trades, sharpe, tj = row
    tlist = json.loads(tj)
    if not tlist:
        print("%-12s %-18s %-8s %-4s %6d %8.3f %8s %8s %8s %8s %s" % (
            cid, strat, sym, tf, trades, sharpe, "N/A", "N/A", "N/A", "N/A", "NO TRADES"))
        continue
    pnls = np.array([t["net_pnl"] for t in tlist])

    # Empirical moments
    mu = pnls.mean()
    std = pnls.std(ddof=1)
    if std > 1e-10 and len(pnls) > 3:
        z = (pnls - mu) / std
        skew = float(np.mean(z ** 3))
        kurt = float(np.mean(z ** 4) - 3)  # excess kurtosis
    else:
        skew, kurt = 0.0, 0.0

    # DSR with defaults (skew=0, kurt=3)
    dsr_default = deflated_sharpe_ratio(sharpe, 500, trades, sharpe_annualization_factor=1.0)  # TODO(DSR-AUDIT): unaudited call site, factor=1.0 preserves prior (possibly-incorrect) behavior — see MATH_CORRECTNESS_AUDIT.md
    dsr_def_val = 1.0 - dsr_default.probability_alpha

    # DSR with empirical moments (clamp kurtosis to avoid math domain error)
    kurt_clamped = max(kurt, -2.0)  # kurtosis < -2 can cause sqrt of negative
    try:
        dsr_empirical = deflated_sharpe_ratio(sharpe, 500, trades, sharpe_annualization_factor=1.0, skewness=skew, kurtosis=kurt_clamped)  # TODO(DSR-AUDIT): unaudited call site, factor=1.0 preserves prior (possibly-incorrect) behavior — see MATH_CORRECTNESS_AUDIT.md
        dsr_emp_val = 1.0 - dsr_empirical.probability_alpha
    except (ValueError, ZeroDivisionError):
        dsr_emp_val = float("nan")

    # Bootstrap: simple block bootstrap for Sharpe CI
    n_boot = 2000
    rng = np.random.default_rng(42)
    boot_sharpes = []
    for _ in range(n_boot):
        # Block bootstrap (block size = sqrt(T))
        block_size = max(1, int(np.sqrt(trades)))
        n_blocks = max(1, trades // block_size)
        indices = []
        for _ in range(n_blocks):
            start = rng.integers(0, max(1, len(pnls) - block_size))
            indices.extend(range(start, min(start + block_size, len(pnls))))
        indices = indices[:trades]
        if len(indices) < 10:
            continue
        sample = pnls[indices]
        s_std = sample.std(ddof=1)
        if s_std > 1e-10:
            boot_sharpes.append(float(sample.mean() / s_std * np.sqrt(252)))

    if boot_sharpes:
        boot_arr = np.array(boot_sharpes)
        ci_low = float(np.percentile(boot_arr, 2.5))
        ci_high = float(np.percentile(boot_arr, 97.5))
        boot_passes = ci_low > 0
        boot_str = "PASS [%.2f, %.2f]" % (ci_low, ci_high) if boot_passes else "FAIL [%.2f, %.2f]" % (ci_low, ci_high)
    else:
        boot_str = "NO_BOOT"

    print("%-12s %-18s %-8s %-4s %6d %8.3f %8.2f %8.2f %8.4f %8.4f %s" % (
        cid, strat, sym, tf, trades, sharpe, skew, kurt,
        dsr_def_val, dsr_emp_val, boot_str))

print()
print("DSR(def) = DSR with default skew=0, kurt=3 (Normal assumption)")
print("DSR(emp) = DSR with empirical skew/kurtosis from actual trade P&L")
print("DSR_boot = Bootstrap 95% CI on Sharpe (block bootstrap, B=2000)")
print("PASS = CI lower bound > 0")
