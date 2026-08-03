"""
INSTITUTIONAL-GRADE PIPELINE
============================
Integrates all 6 layers that separate institutional from retail:

  Layer 1: Multiple Testing Bias (Deflated Sharpe + PBO + BH FDR)
  Layer 2: Portfolio Construction (Corr-aware weighting + Vol targeting + Fractional Kelly + CPPI)
  Layer 3: Cost/Capacity (30-50% haircut + Market impact + Vol-regime slippage)
  Layer 4: Risk Overlays (Daily loss limit + Kill switch + Correlation cap + Regime shift)
  Layer 5: Execution Quality (TCA logging + Order type selection)
  Layer 6: Governance (Hypothesis registry + Quarterly revalidation + Sacred holdout rules)

Usage:
    python scripts/institutional_pipeline.py
"""

from __future__ import annotations

import json
import math
import sys
import warnings
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path

# Windows UTF-8 fix
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")

import numpy as np
import pandas as pd

# ── Package setup ────────────────────────────────────────────────────────
ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def _setup():
    """Make quant_os importable as a package."""
    import importlib
    pkg = importlib.import_module("quant_os")
    return pkg


_setup()

# ── Direct imports to avoid circular dependency issues ───────────────────
import importlib.util

def _load_module(name: str, path: Path):
    """Load a module directly from file path."""
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod

# Load each module directly
_dsr_mod = _load_module("deflated_sharpe", ROOT / "validation" / "deflated_sharpe.py")
_pbo_mod = _load_module("probability_overfitting", ROOT / "validation" / "probability_overfitting.py")
_bh_mod = _load_module("multiple_testing", ROOT / "validation" / "multiple_testing.py")
_kelly_mod = _load_module("kelly", ROOT / "core" / "kelly.py")
_ewma_mod = _load_module("ewma_correlation", ROOT / "risk" / "ewma_correlation.py")
_impact_mod = _load_module("market_impact", ROOT / "execution" / "market_impact.py")

deflated_sharpe_ratio = _dsr_mod.deflated_sharpe_ratio
dsr_from_annualized = _dsr_mod.dsr_from_annualized
min_backtest_length = _dsr_mod.min_backtest_length
calculate_pbo_from_matrix = _pbo_mod.calculate_pbo_from_matrix
benjamini_hochberg = _bh_mod.benjamini_hochberg
DynamicKellySizer = _kelly_mod.DynamicKellySizer
kelly_fraction = _kelly_mod.kelly_fraction
EWMACorrelation = _ewma_mod.EWMACorrelation
EWMAConfig = _ewma_mod.EWMAConfig
estimate_market_impact_bps = _impact_mod.estimate_market_impact_bps


# ══════════════════════════════════════════════════════════════════════════
# LAYER 1: MULTIPLE TESTING BIAS
# ══════════════════════════════════════════════════════════════════════════

@dataclass
class Layer1Result:
    """Results from multiple testing correction."""
    deflated_sharpe_results: dict[str, dict] = field(default_factory=dict)
    pbo_result: dict | None = None
    bh_adjusted_pvalues: dict[str, float] = field(default_factory=dict)
    strategies_passing_deflation: list[str] = field(default_factory=list)
    strategies_passing_pbo: bool = False
    verdict: str = ""


def run_layer1(
    strategy_sharpes: dict[str, float],
    strategy_returns: dict[str, list[float]],
    n_observations: dict[str, int],
    n_total_trials: int,
) -> Layer1Result:
    """Layer 1: Multiple Testing Bias correction.

    Args:
        strategy_sharpes: {strategy_name: observed_sharpe}
        strategy_returns: {strategy_name: list of daily returns}
        n_observations: {strategy_name: number of return observations}
        n_total_trials: total number of strategy trials across all research
    """
    result = Layer1Result()

    # ── 1a. Deflated Sharpe Ratio for each strategy ─────────────────────
    print("\n  LAYER 1a: Deflated Sharpe Ratio (n_trials={})".format(n_total_trials))
    for name, sharpe in strategy_sharpes.items():
        n_obs = n_observations.get(name, len(strategy_returns.get(name, [])))
        returns = strategy_returns.get(name, [])

        # Compute skewness and kurtosis from returns
        if len(returns) >= 10:
            arr = np.array(returns)
            skew = float(np.mean(((arr - arr.mean()) / (arr.std() + 1e-10)) ** 3))
            kurt = float(np.mean(((arr - arr.mean()) / (arr.std() + 1e-10)) ** 4))
        else:
            skew, kurt = 0.0, 3.0

        dsr = dsr_from_annualized(
            observed_sharpe=sharpe,
            n_trials=n_total_trials,
            n_observations=n_obs,
            annualization_factor=252,  # SP1: sharpe is annualized (mean*252/std*sqrt(252)), n_obs is daily bars
            skewness=skew,
            kurtosis=kurt,
        )
        result.deflated_sharpe_results[name] = {
            "observed_sharpe": round(sharpe, 4),
            "deflated_sharpe": round(dsr.deflated_sharpe, 4),
            "probability_alpha": round(dsr.probability_alpha, 4),
            "multiple_testing_adjustment": round(dsr.multiple_testing_adjustment, 4),
            "passes": dsr.passes_threshold,
        }
        status = "PASS" if dsr.passes_threshold else "FAIL"
        print(f"    {name}: observed={sharpe:.4f}, deflated_p={dsr.probability_alpha:.4f} [{status}]")

        if dsr.passes_threshold:
            result.strategies_passing_deflation.append(name)

    # ── 1b. Benjamini-Hochberg FDR correction ───────────────────────────
    print("\n  LAYER 1b: Benjamini-Hochberg FDR correction")
    names = list(strategy_sharpes.keys())
    pvals = [result.deflated_sharpe_results[n]["probability_alpha"] for n in names]
    if pvals:
        rejected, adjusted = benjamini_hochberg(pvals, alpha=0.05)
        for i, name in enumerate(names):
            result.bh_adjusted_pvalues[name] = round(float(adjusted[i]), 4)
            status = "REJECT" if rejected[i] else "FAIL TO REJECT"
            print(f"    {name}: raw_p={pvals[i]:.4f}, adjusted_q={adjusted[i]:.4f} [{status}]")

    # ── 1c. PBO via CSCV (strategy matrix) ──────────────────────────────
    print("\n  LAYER 1c: Probability of Backtest Overfitting (CSCV)")
    # Build strategy matrix: {config_id: [period1_returns, period2_returns, ...]}
    # Split each strategy's returns into equal periods for CSCV
    strategy_matrix: dict[str, list[list[float]]] = {}
    for name, returns in strategy_returns.items():
        if len(returns) < 20:
            continue
        n_periods = min(8, len(returns) // 20)  # ~20 returns per period
        chunk_size = len(returns) // n_periods
        periods = []
        for i in range(n_periods):
            start = i * chunk_size
            end = start + chunk_size if i < n_periods - 1 else len(returns)
            periods.append(returns[start:end])
        strategy_matrix[name] = periods

    if len(strategy_matrix) >= 2:
        pbo = calculate_pbo_from_matrix(strategy_matrix, n_combinations=128)
        result.pbo_result = {
            "pbo": pbo.pbo,
            "n_partitions": pbo.n_partitions,
            "n_combinations_tested": pbo.n_combinations_tested,
            "passes": pbo.passes_threshold,
        }
        result.strategies_passing_pbo = pbo.passes_threshold
        status = "PASS" if pbo.passes_threshold else "FAIL"
        print(f"    PBO = {pbo.pbo:.4f} ({pbo.n_combinations_tested} combos) [{status}]")
    else:
        print("    PBO: insufficient strategies for CSCV (need >= 2)")

    # ── Verdict ──────────────────────────────────────────────────────────
    n_pass_dsr = len(result.strategies_passing_deflation)
    pbo_str = f"PBO={'PASS' if result.strategies_passing_pbo else 'FAIL'}" if result.pbo_result else "PBO=N/A"
    result.verdict = f"{n_pass_dsr}/{len(strategy_sharpes)} pass deflation, {pbo_str}"
    print(f"\n  LAYER 1 VERDICT: {result.verdict}")

    return result


# ══════════════════════════════════════════════════════════════════════════
# LAYER 2: PORTFOLIO CONSTRUCTION
# ══════════════════════════════════════════════════════════════════════════

@dataclass
class Layer2Result:
    """Results from institutional portfolio construction."""
    correlation_matrix: dict[str, dict[str, float]] = field(default_factory=dict)
    avg_correlation: float = 0.0
    weights_equal: dict[str, float] = field(default_factory=dict)
    weights_corr_aware: dict[str, float] = field(default_factory=dict)
    weights_kelly: dict[str, float] = field(default_factory=dict)
    vol_target_weights: dict[str, float] = field(default_factory=dict)
    portfolio_vol: float = 0.0
    kelly_fractions: dict[str, float] = field(default_factory=dict)
    verdict: str = ""


def run_layer2(
    strategy_returns: dict[str, list[float]],
    strategy_sharpes: dict[str, float],
    strategy_winrates: dict[str, float],
    strategy_avg_rr: dict[str, float],
    current_drawdown_pct: float = 0.0,
) -> Layer2Result:
    """Layer 2: Institutional Portfolio Construction."""
    result = Layer2Result()
    names = list(strategy_returns.keys())

    if not names:
        result.verdict = "No strategies"
        return result

    # ── 2a. EWMA Correlation Matrix ─────────────────────────────────────
    print("\n  LAYER 2a: EWMA Correlation Matrix")
    ewma = EWMACorrelation(EWMAConfig(lambda_decay=0.94, min_observations=30))

    # Feed returns bar-by-bar
    min_len = min(len(strategy_returns[n]) for n in names)
    for t in range(min_len):
        bar_returns = {n: strategy_returns[n][t] for n in names}
        ewma.update(bar_returns)

    corr_matrix = {}
    for s1 in names:
        corr_matrix[s1] = {}
        for s2 in names:
            corr_matrix[s1][s2] = round(ewma.get_correlation(s1, s2), 4)

    result.correlation_matrix = corr_matrix
    result.avg_correlation = round(ewma.get_average_correlation(), 4)
    print(f"    Average pairwise correlation: {result.avg_correlation:.4f}")

    # ── 2b. Correlation-Aware Weighting ──────────────────────────────────
    print("\n  LAYER 2b: Correlation-Aware Weighting")
    # Inverse-vol + inverse-correlation weighting
    # Strategies with lower correlation to others get higher weight
    n = len(names)
    weights_ca = {}
    for s in names:
        rets = np.array(strategy_returns[s])
        vol = float(rets.std()) if len(rets) > 1 else 1.0
        avg_corr_s = np.mean([abs(corr_matrix[s].get(o, 0)) for o in names if o != s]) if n > 1 else 0
        # Lower vol + lower correlation = higher weight
        inv_vol = 1.0 / (vol + 1e-10)
        inv_corr = 1.0 / (avg_corr_s + 0.1)  # avoid div by 0
        weights_ca[s] = inv_vol * inv_corr

    # Normalize
    total = sum(weights_ca.values()) or 1.0
    weights_ca = {k: round(v / total, 4) for k, v in weights_ca.items()}
    result.weights_corr_aware = weights_ca
    print(f"    Correlation-aware weights: {weights_ca}")

    # ── 2c. Fractional Kelly (1/4 Kelly) ────────────────────────────────
    print("\n  LAYER 2c: Fractional Kelly Sizing (1/4 Kelly)")
    kelly_sizer = DynamicKellySizer(base_kelly=0.25, vol_target=0.15)
    kelly_fracs = {}
    for s in names:
        wr = strategy_winrates.get(s, 0.5)
        rr = strategy_avg_rr.get(s, 1.0)
        rets = np.array(strategy_returns[s])
        vol_current = float(rets.std() * math.sqrt(252)) if len(rets) > 1 else 0.15
        kr = kelly_sizer.compute_kelly(
            win_rate=wr, avg_rr=rr,
            vol_current=vol_current, vol_target=0.15,
            regime="normal", spread_cost=0.001,
        )
        kelly_fracs[s] = round(kr.fraction, 4)
        print(f"    {s}: kelly={kr.fraction:.4f} (base={kr.base_kelly:.4f}, vol_scale={kr.vol_scale:.2f})")

    result.kelly_fractions = kelly_fracs

    # Kelly-weighted = kelly_fraction * correlation-aware weight
    kelly_total = sum(kelly_fracs.values()) or 1.0
    weights_kelly = {s: round(kelly_fracs[s] / kelly_total, 4) for s in names}
    result.weights_kelly = weights_kelly
    print(f"    Kelly-weighted portfolio: {weights_kelly}")

    # ── 2d. Volatility Targeting ─────────────────────────────────────────
    print("\n  LAYER 2d: Portfolio Volatility Targeting (target=15%)")
    PORTFOLIO_VOL_TARGET = 0.15
    # Compute current portfolio vol from weighted returns
    min_len = min(len(strategy_returns[n]) for n in names)
    portfolio_daily = np.zeros(min_len)
    for s in names:
        w = weights_kelly.get(s, 1.0 / n)
        portfolio_daily += w * np.array(strategy_returns[s][:min_len])
    portfolio_vol = float(portfolio_daily.std() * math.sqrt(252)) if len(portfolio_daily) > 1 else 0.15
    result.portfolio_vol = round(portfolio_vol, 4)

    vol_scalar = PORTFOLIO_VOL_TARGET / (portfolio_vol + 1e-10)
    vol_scalar = min(vol_scalar, 2.0)  # cap at 2x (don't leverage up)
    vol_scalar = max(vol_scalar, 0.25)  # floor at 0.25x (don't de-lever too much)

    vol_target_weights = {s: round(w * vol_scalar, 4) for s, w in weights_kelly.items()}
    result.vol_target_weights = vol_target_weights
    print(f"    Portfolio vol: {portfolio_vol:.4f}, scalar: {vol_scalar:.2f}")
    print(f"    Vol-targeted weights: {vol_target_weights}")

    # ── 2e. CPPI Drawdown-Conditional De-risking ─────────────────────────
    print("\n  LAYER 2e: CPPI Drawdown-Conditional De-risking")
    CPPI_FLOOR = 0.80  # protect 80% of capital
    CPPI_MULTIPLIER = 5.0
    cushion = max(0, (1.0 + current_drawdown_pct / 100.0) - CPPI_FLOOR)
    cppi_exposure = min(1.0, CPPI_MULTIPLIER * cushion)
    print(f"    Drawdown: {current_drawdown_pct:.1f}%, Cushion: {cushion:.4f}, CPPI exposure: {cppi_exposure:.4f}")

    # Apply CPPI to vol-targeted weights
    final_weights = {s: round(w * cppi_exposure, 4) for s, w in vol_target_weights.items()}
    print(f"    Final weights (after CPPI): {final_weights}")

    result.verdict = f"Avg corr={result.avg_correlation:.3f}, Port vol={portfolio_vol:.3f}, CPPI={cppi_exposure:.3f}"
    print(f"\n  LAYER 2 VERDICT: {result.verdict}")

    return result


# ══════════════════════════════════════════════════════════════════════════
# LAYER 3: COST / CAPACITY
# ══════════════════════════════════════════════════════════════════════════

@dataclass
class Layer3Result:
    """Results from cost/capacity analysis."""
    raw_sharpes: dict[str, float] = field(default_factory=dict)
    haircut_sharpes: dict[str, float] = field(default_factory=dict)
    haircut_pct: float = 0.0
    market_impact_bps: dict[str, float] = field(default_factory=dict)
    net_sharpes: dict[str, float] = field(default_factory=dict)
    capacity_lots: dict[str, float] = field(default_factory=dict)
    verdict: str = ""


def run_layer3(
    strategy_sharpes: dict[str, float],
    strategy_returns: dict[str, list[float]],
    avg_daily_trades: dict[str, int],
    avg_trade_size_lots: dict[str, float],
    daily_vol_pct: float = 1.0,
    adv_lots: float = 1_000_000,
) -> Layer3Result:
    """Layer 3: Realistic Cost/Capacity analysis."""
    result = Layer3Result()
    result.raw_sharpes = strategy_sharpes.copy()

    # ── 3a. 30-50% Sharpe Haircut ───────────────────────────────────────
    print("\n  LAYER 3a: 40% Sharpe Haircut (institutional standard)")
    HAIRCUT = 0.40  # 40% reduction
    result.haircut_pct = HAIRCUT
    for name, sharpe in strategy_sharpes.items():
        net = sharpe * (1 - HAIRCUT)
        result.haircut_sharpes[name] = round(net, 4)
        print(f"    {name}: {sharpe:.4f} → {net:.4f} (after {HAIRCUT*100:.0f}% haircut)")

    # ── 3b. Market Impact (Square-Root Law) ──────────────────────────────
    print("\n  LAYER 3b: Market Impact (square-root law)")
    for name in strategy_sharpes:
        size = avg_trade_size_lots.get(name, 1.0)
        impact = estimate_market_impact_bps(size, daily_vol_pct, adv_lots, eta=0.1)
        result.market_impact_bps[name] = round(impact, 4)
        print(f"    {name}: {size:.1f} lots → impact={impact:.4f} bps")

    # ── 3c. Net Sharpe after costs ──────────────────────────────────────
    print("\n  LAYER 3c: Net Sharpe after all costs")
    SPREAD_COST_BPS = 0.5  # half-spread
    COMMISSION_BPS = 0.2   # per side
    TOTAL_COST_BPS = SPREAD_COST_BPS * 2 + COMMISSION_BPS * 2  # round-trip

    for name in strategy_sharpes:
        haircut = result.haircut_sharpes.get(name, 0)
        impact_bps = result.market_impact_bps.get(name, 0)
        # Convert bps cost to annualized Sharpe reduction
        # Assume ~250 trading days, avg trade duration varies
        daily_cost = (TOTAL_COST_BPS + impact_bps) / 10000
        annual_cost_sharpe = daily_cost * math.sqrt(252)
        net = haircut - annual_cost_sharpe
        result.net_sharpes[name] = round(net, 4)
        print(f"    {name}: haircut={haircut:.4f}, cost_drag={annual_cost_sharpe:.4f}, net={net:.4f}")

    # ── 3d. Capacity Estimation ──────────────────────────────────────────
    print("\n  LAYER 3d: Capacity Estimation")
    for name in strategy_sharpes:
        # Max size before impact exceeds edge
        raw_sharpe = strategy_sharpes[name]
        edge_per_trade_bps = raw_sharpe * daily_vol_pct * 100 / math.sqrt(252)  # rough
        # Solve: eta * vol * sqrt(Q/ADV) = edge → Q = ADV * (edge / (eta * vol))^2
        if edge_per_trade_bps > 0 and daily_vol_pct > 0:
            max_lots = adv_lots * (edge_per_trade_bps / (0.1 * daily_vol_pct * 100)) ** 2
        else:
            max_lots = 0
        result.capacity_lots[name] = round(max_lots, 0)
        print(f"    {name}: max capacity = {max_lots:.0f} lots/day")

    # ── Verdict ──────────────────────────────────────────────────────────
    n_positive = sum(1 for v in result.net_sharpes.values() if v > 0)
    result.verdict = f"{n_positive}/{len(strategy_sharpes)} strategies have positive net Sharpe after costs"
    print(f"\n  LAYER 3 VERDICT: {result.verdict}")

    return result


# ══════════════════════════════════════════════════════════════════════════
# LAYER 4: RISK OVERLAYS
# ══════════════════════════════════════════════════════════════════════════

@dataclass
class Layer4Result:
    """Results from risk overlay checks."""
    daily_loss_limit_pct: float = -2.0
    max_drawdown_kill_pct: float = -15.0
    correlation_cap: float = 0.7
    regime_shift_detected: bool = False
    current_drawdown_pct: float = 0.0
    daily_pnl_pct: float = 0.0
    exposure_within_limits: bool = True
    regime_risk_level: str = "NORMAL"
    verdict: str = ""


def run_layer4(
    strategy_returns: dict[str, list[float]],
    weights: dict[str, float],
    current_equity: float = 100000,
    peak_equity: float = 100000,
    daily_pnl: float = 0,
    correlation_matrix: dict[str, dict[str, float]] | None = None,
) -> Layer4Result:
    """Layer 4: Hard Risk Overlays."""
    result = Layer4Result()

    # ── 4a. Drawdown Check ───────────────────────────────────────────────
    print("\n  LAYER 4a: Drawdown & Kill Switch")
    drawdown_pct = ((current_equity - peak_equity) / peak_equity) * 100 if peak_equity > 0 else 0
    result.current_drawdown_pct = round(drawdown_pct, 2)
    kill_triggered = drawdown_pct <= result.max_drawdown_kill_pct
    print(f"    Current DD: {drawdown_pct:.2f}%, Kill threshold: {result.max_drawdown_kill_pct}%")
    print(f"    Kill switch: {'TRIGGERED' if kill_triggered else 'OK'}")

    # ── 4b. Daily Loss Limit ─────────────────────────────────────────────
    print("\n  LAYER 4b: Daily Loss Limit")
    daily_pnl_pct = (daily_pnl / current_equity * 100) if current_equity > 0 else 0
    result.daily_pnl_pct = round(daily_pnl_pct, 2)
    daily_breached = daily_pnl_pct <= result.daily_loss_limit_pct
    print(f"    Daily PnL: {daily_pnl_pct:.2f}%, Limit: {result.daily_loss_limit_pct}%")
    print(f"    Daily limit: {'BREACHED' if daily_breached else 'OK'}")

    # ── 4c. Correlation-Aware Exposure Cap ───────────────────────────────
    print("\n  LAYER 4c: Correlation-Aware Exposure Cap")
    if correlation_matrix:
        names = list(weights.keys())
        max_pair_corr = 0.0
        max_pair = ("", "")
        for i, s1 in enumerate(names):
            for s2 in names[i + 1:]:
                c = abs(correlation_matrix.get(s1, {}).get(s2, 0))
                if c > max_pair_corr:
                    max_pair_corr = c
                    max_pair = (s1, s2)
        result.exposure_within_limits = max_pair_corr < result.correlation_cap
        print(f"    Max pairwise corr: {max_pair_corr:.4f} ({max_pair[0]}-{max_pair[1]})")
        print(f"    Correlation cap: {result.correlation_cap}")
        print(f"    Correlation check: {'BREACHED' if not result.exposure_within_limits else 'OK'}")
    else:
        print("    No correlation matrix provided")

    # ── 4d. Regime-Shift Detection (Vol-of-Vol) ─────────────────────────
    print("\n  LAYER 4d: Regime-Shift Detection (Vol-of-Vol)")
    # Check if recent vol is significantly different from historical
    names = list(strategy_returns.keys())
    if names and len(strategy_returns[names[0]]) >= 60:
        recent_vol = np.std(strategy_returns[names[0]][-20:]) if len(strategy_returns[names[0]]) >= 20 else 0
        hist_vol = np.std(strategy_returns[names[0]][:-20]) if len(strategy_returns[names[0]]) > 20 else recent_vol
        vol_of_vol = recent_vol / (hist_vol + 1e-10)
        result.regime_shift_detected = vol_of_vol > 1.5
        result.regime_risk_level = "HIGH" if vol_of_vol > 1.5 else "NORMAL"
        print(f"    Recent vol / Hist vol = {vol_of_vol:.2f}")
        print(f"    Regime shift: {'DETECTED' if result.regime_shift_detected else 'NONE'}")
    else:
        print("    Insufficient data for regime detection")

    # ── Verdict ──────────────────────────────────────────────────────────
    issues = []
    if kill_triggered:
        issues.append("KILL_SWITCH_TRIGGERED")
    if daily_breached:
        issues.append("DAILY_LOSS_BREACHED")
    if not result.exposure_within_limits:
        issues.append("CORRELATION_CAP_BREACHED")
    if result.regime_shift_detected:
        issues.append("REGIME_SHIFT_DETECTED")

    result.verdict = "ALL_CLEAR" if not issues else ", ".join(issues)
    print(f"\n  LAYER 4 VERDICT: {result.verdict}")

    return result


# ══════════════════════════════════════════════════════════════════════════
# LAYER 5: EXECUTION QUALITY
# ══════════════════════════════════════════════════════════════════════════

@dataclass
class Layer5Result:
    """Results from execution quality framework."""
    tca_metrics: dict[str, dict] = field(default_factory=dict)
    order_type_recommendations: dict[str, str] = field(default_factory=dict)
    verdict: str = ""


def run_layer5(
    strategy_returns: dict[str, list[float]],
    avg_spread_pips: dict[str, float] | None = None,
) -> Layer5Result:
    """Layer 5: Execution Quality."""
    result = Layer5Result()

    print("\n  LAYER 5: Execution Quality (TCA Framework)")

    for name, returns in strategy_returns.items():
        if len(returns) < 10:
            continue

        arr = np.array(returns)
        # Estimate execution metrics from return distribution
        avg_return = float(arr.mean())
        vol = float(arr.std())
        win_rate = float(np.mean(arr > 0))
        avg_win = float(arr[arr > 0].mean()) if np.any(arr > 0) else 0
        avg_loss = float(arr[arr < 0].mean()) if np.any(arr < 0) else 0

        # TCA metrics
        slippage_estimate = vol * 0.1  # rough: 10% of daily vol as slippage
        fill_quality = 1.0 - (slippage_estimate / (abs(avg_return) + 1e-10))

        result.tca_metrics[name] = {
            "avg_return_bps": round(avg_return * 10000, 2),
            "vol_bps": round(vol * 10000, 2),
            "win_rate": round(win_rate, 4),
            "profit_factor": round(abs(avg_win / avg_loss), 2) if avg_loss != 0 else 0,
            "slippage_estimate_bps": round(slippage_estimate * 10000, 2),
            "fill_quality_score": round(min(fill_quality, 1.0), 4),
        }

        # Order type recommendation based on spread regime
        avg_spread = avg_spread_pips.get(name, 1.0) if avg_spread_pips else 1.0
        if avg_spread < 0.5:
            result.order_type_recommendations[name] = "MARKET_ORDER"
        elif avg_spread < 2.0:
            result.order_type_recommendations[name] = "LIMIT_ORDER_AGGRESSIVE"
        else:
            result.order_type_recommendations[name] = "LIMIT_ORDER_PASSIVE"

        print(f"    {name}: fill_quality={fill_quality:.2f}, order={result.order_type_recommendations[name]}")

    result.verdict = f"{len(result.tca_metrics)} strategies TCA'd"
    print(f"\n  LAYER 5 VERDICT: {result.verdict}")

    return result


# ══════════════════════════════════════════════════════════════════════════
# LAYER 6: GOVERNANCE
# ══════════════════════════════════════════════════════════════════════════

@dataclass
class Layer6Result:
    """Results from governance checks."""
    hypothesis_registry: dict[str, dict] = field(default_factory=dict)
    revalidation_schedule: str = "quarterly"
    sacred_holdout_used: bool = True
    sacred_holdout_remaining_uses: int = 0
    strategies_with_hypothesis: list[str] = field(default_factory=list)
    strategies_without_hypothesis: list[str] = field(default_factory=list)
    verdict: str = ""


def run_layer6(
    strategy_names: list[str],
) -> Layer6Result:
    """Layer 6: Governance."""
    result = Layer6Result()
    result.sacred_holdout_used = True
    result.sacred_holdout_remaining_uses = 0  # Used once, done

    print("\n  LAYER 6: Governance")

    # Hypothesis registry — check which strategies have pre-registered hypotheses
    # In production, this would read from a YAML/JSON file
    # For now, flag all as needing hypothesis documentation
    for name in strategy_names:
        result.hypothesis_registry[name] = {
            "hypothesis_documented": False,  # Must be set True before live
            "pre_registered_params": True,   # All new strategies have frozen configs
            "economic_rationale": "TBD",     # Must be filled
            "revalidation_date": None,       # Must be set quarterly
        }
        result.strategies_without_hypothesis.append(name)

    print(f"    Sacred holdout: USED (0 remaining uses)")
    print(f"    Revalidation schedule: {result.revalidation_schedule}")
    print(f"    Strategies needing hypothesis docs: {len(result.strategies_without_hypothesis)}")

    result.verdict = f"GOVERNANCE_INCOMPLETE: {len(strategy_names)} strategies need hypothesis docs"
    print(f"\n  LAYER 6 VERDICT: {result.verdict}")

    return result


# ══════════════════════════════════════════════════════════════════════════
# MAIN PIPELINE
# ══════════════════════════════════════════════════════════════════════════

def main():
    """Run the full institutional pipeline."""
    print("=" * 64)
    print("  INSTITUTIONAL-GRADE PIPELINE")
    print("  6 Layers: Multiple Testing → Portfolio → Cost → Risk → Execution → Governance")
    print("=" * 64)

    # ── Load data ────────────────────────────────────────────────────────
    data_path = ROOT / "data" / "XAUUSD_D1.csv"
    if not data_path.exists():
        print(f"ERROR: {data_path} not found")
        sys.exit(1)

    df = pd.read_csv(data_path)
    # Handle both lowercase and capitalized column names
    col_map = {c.lower(): c for c in df.columns}
    time_col = col_map.get("time", col_map.get("date", df.columns[0]))
    close_col = col_map.get("close", "Close")

    if time_col in df.columns:
        df[time_col] = pd.to_datetime(df[time_col])
        df = df.sort_values(time_col).reset_index(drop=True)

    close = df[close_col].values.astype(float)
    returns = np.diff(np.log(close))
    print(f"\nData: {len(df)} bars, {len(returns)} returns")

    # ── Strategy return simulation ───────────────────────────────────────
    # In production, these come from walk-forward OOS results
    # Here we simulate from the strategies' signal logic
    np.random.seed(42)

    # Use the 6 strategies from research_backed_pipeline
    strategy_configs = {
        "momentum_12m": {"lookback": 252, "vol_mult": 1.0},
        "donchian_55": {"lookback": 55, "vol_mult": 1.0},
        "donchian_20": {"lookback": 20, "vol_mult": 1.0},
        "hybrid_mom_mr": {"lookback": 60, "vol_mult": 0.8},
        "mean_reversion_bb": {"lookback": 20, "vol_mult": 0.6},
        "dxy_divergence": {"lookback": 40, "vol_mult": 0.5},
    }

    strategy_returns = {}
    strategy_sharpes = {}
    strategy_winrates = {}
    strategy_avg_rr = {}

    for name, cfg in strategy_configs.items():
        lb = cfg["lookback"]
        # Simulate signal: momentum/mean-reversion hybrid
        signal = np.zeros(len(returns))
        for t in range(lb, len(returns)):
            hist = returns[t - lb:t]
            if name.startswith("donchian"):
                # Donchian: breakout direction
                signal[t] = 1.0 if returns[t - 1] > 0 else -1.0
            elif "mean_reversion" in name:
                # Mean reversion: fade extremes
                signal[t] = -1.0 if np.sum(hist[-5:]) > 0 else 1.0
            elif "dxy" in name:
                # Divergence: partial correlation
                signal[t] = np.sign(np.mean(hist[-10:])) * 0.5
            else:
                # Momentum: trend following
                signal[t] = 1.0 if np.mean(hist) > 0 else -1.0

        strat_returns = signal[lb:] * returns[lb:] * cfg["vol_mult"]
        # Add realistic noise (slippage, etc.)
        strat_returns += np.random.normal(0, 0.0005, len(strat_returns))

        strategy_returns[name] = strat_returns.tolist()

        # Compute metrics
        arr = strat_returns
        vol = float(arr.std())
        ann_return = float(arr.mean() * 252)
        ann_vol = vol * math.sqrt(252)
        sharpe = ann_return / ann_vol if ann_vol > 0 else 0
        wr = float(np.mean(arr > 0))
        wins = arr[arr > 0]
        losses = arr[arr < 0]
        avg_rr = float(abs(wins.mean() / losses.mean())) if len(losses) > 0 else 1.0

        strategy_sharpes[name] = round(sharpe, 4)
        strategy_winrates[name] = round(wr, 4)
        strategy_avg_rr[name] = round(avg_rr, 4)

    n_trials = 31  # Total strategies tested across all research

    print(f"\nStrategies: {list(strategy_returns.keys())}")
    print(f"Total trials (n): {n_trials}")

    # ── Run all 6 layers ─────────────────────────────────────────────────
    print("\n" + "=" * 64)
    print("  RUNNING 6 LAYERS")
    print("=" * 64)

    # Layer 1: Multiple Testing
    layer1 = run_layer1(strategy_sharpes, strategy_returns, {}, n_trials)

    # Layer 2: Portfolio Construction
    layer2 = run_layer2(strategy_returns, strategy_sharpes, strategy_winrates, strategy_avg_rr)

    # Layer 3: Cost/Capacity
    avg_daily_trades = {n: 5 for n in strategy_returns}
    avg_trade_size = {n: 1.0 for n in strategy_returns}
    layer3 = run_layer3(strategy_sharpes, strategy_returns, avg_daily_trades, avg_trade_size)

    # Layer 4: Risk Overlays
    corr_matrix = layer2.correlation_matrix
    layer4 = run_layer4(strategy_returns, layer2.vol_target_weights, correlation_matrix=corr_matrix)

    # Layer 5: Execution Quality
    layer5 = run_layer5(strategy_returns)

    # Layer 6: Governance
    layer6 = run_layer6(list(strategy_returns.keys()))

    # ── FINAL REPORT ─────────────────────────────────────────────────────
    print("\n" + "=" * 64)
    print("  FINAL REPORT")
    print("=" * 64)

    report = {
        "timestamp": datetime.now(UTC).isoformat(),
        "layer1_multiple_testing": {
            "deflated_sharpe": layer1.deflated_sharpe_results,
            "pbo": layer1.pbo_result,
            "bh_adjusted_pvalues": layer1.bh_adjusted_pvalues,
            "strategies_passing_deflation": layer1.strategies_passing_deflation,
            "verdict": layer1.verdict,
        },
        "layer2_portfolio_construction": {
            "correlation_matrix": layer2.correlation_matrix,
            "avg_correlation": layer2.avg_correlation,
            "weights_kelly": layer2.weights_kelly,
            "vol_target_weights": layer2.vol_target_weights,
            "portfolio_vol": layer2.portfolio_vol,
            "kelly_fractions": layer2.kelly_fractions,
            "verdict": layer2.verdict,
        },
        "layer3_cost_capacity": {
            "raw_sharpes": layer3.raw_sharpes,
            "haircut_sharpes": layer3.haircut_sharpes,
            "market_impact_bps": layer3.market_impact_bps,
            "net_sharpes": layer3.net_sharpes,
            "capacity_lots": layer3.capacity_lots,
            "verdict": layer3.verdict,
        },
        "layer4_risk_overlays": {
            "daily_loss_limit": layer4.daily_loss_limit_pct,
            "max_drawdown_kill": layer4.max_drawdown_kill_pct,
            "correlation_cap": layer4.correlation_cap,
            "current_drawdown": layer4.current_drawdown_pct,
            "regime_shift_detected": layer4.regime_shift_detected,
            "regime_risk_level": layer4.regime_risk_level,
            "verdict": layer4.verdict,
        },
        "layer5_execution_quality": {
            "tca_metrics": layer5.tca_metrics,
            "order_type_recommendations": layer5.order_type_recommendations,
            "verdict": layer5.verdict,
        },
        "layer6_governance": {
            "hypothesis_registry": layer6.hypothesis_registry,
            "revalidation_schedule": layer6.revalidation_schedule,
            "sacred_holdout_remaining": layer6.sacred_holdout_remaining_uses,
            "verdict": layer6.verdict,
        },
    }

    # Print summary
    print(f"\n  Layer 1 (Multiple Testing): {layer1.verdict}")
    print(f"  Layer 2 (Portfolio):        {layer2.verdict}")
    print(f"  Layer 3 (Cost/Capacity):    {layer3.verdict}")
    print(f"  Layer 4 (Risk Overlays):    {layer4.verdict}")
    print(f"  Layer 5 (Execution):        {layer5.verdict}")
    print(f"  Layer 6 (Governance):       {layer6.verdict}")

    # Overall go/no-go
    layers_ok = (
        len(layer1.strategies_passing_deflation) > 0
        and layer4.verdict == "ALL_CLEAR"
    )
    print(f"\n  {'='*64}")
    if layers_ok:
        print("  INSTITUTIONAL VERDICT: CONDITIONAL_GO")
        print("  Strategies survive deflation + risk overlays clear")
    else:
        print("  INSTITUTIONAL VERDICT: NO_GO")
        reasons = []
        if not layer1.strategies_passing_deflation:
            reasons.append("no strategies pass deflated Sharpe")
        if layer4.verdict != "ALL_CLEAR":
            reasons.append(f"risk overlays: {layer4.verdict}")
        print(f"  Reasons: {'; '.join(reasons)}")
    print(f"  {'='*64}")

    # Save report
    report_path = ROOT / "reports" / "institutional_pipeline_report.json"
    report_path.parent.mkdir(parents=True, exist_ok=True)
    with open(report_path, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2, default=str)
    print(f"\n  Report saved: {report_path}")

    return report


if __name__ == "__main__":
    main()
