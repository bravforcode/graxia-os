"""
RYDC Validation Runner

Runs the Real-Yield Divergence Continuation hypothesis through the
existing validation pipeline with all gates intact:
- Walk-Forward Analysis (WFA)
- Deflated Sharpe Ratio (DSR)
- Probability of Backtest Overfitting (PBO)
- Bootstrap Sharpe CI
- Statistical significance (p < 0.05)

Pre-registered parameters (cannot be tuned):
- OLS window: 60 days
- Z-score threshold: 1.5
- Hold period: 4 days
- Stop-loss: 1.5 × ATR(14)
- FOMC/CPI exclusion: 48h

Usage:
    python scripts/run_rydc_validation.py
    python scripts/run_rydc_validation.py --data data/rydc/rydc_daily.csv
    python scripts/run_rydc_validation.py --folds 5 --verbose
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path

import numpy as np

# ── Constants ──
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from paper_engine.campaign import get_round_trip_cost_bps  # noqa: E402
from provenance import require_cost_calibrated  # noqa: E402

# 2026-07-30: this backtest previously computed pnl_pct as raw
# (exit-entry)/entry with NO cost term anywhere in the file -- worse
# than the flat-assumed-cost fabrication caught in trial #1030, since it
# didn't even assume a cost. XAUUSD is a fully cost-calibrated symbol
# (real tick spread, $0 commission on Pepperstone metals); apply its
# measured round-trip cost per trade instead of leaving it at zero.
RYDC_SYMBOL = "XAUUSD"


# ── Pre-registered Configuration (Frozen) ──
@dataclass(frozen=True)
class RYDCConfig:
    """Frozen configuration — cannot be changed after instantiation."""

    ols_window: int = 60  # Rolling OLS lookback (trading days)
    z_window: int = 20  # Z-score smoothing window
    z_entry: float = 1.5  # Entry threshold
    z_exit: float = 0.5  # Exit threshold (reversion complete)
    hold_days: int = 4  # Fixed hold period
    atr_period: int = 14  # ATR for stop-loss
    atr_multiplier: float = 1.5  # Stop-loss = 1.5 × ATR
    event_exclusion_hours: int = 48  # Hours before/after FOMC/CPI to exclude


# ── FOMC/CPI Event Dates ──
FOMC_DATES = [
    "2020-01-29",
    "2020-03-03",
    "2020-03-15",
    "2020-04-29",
    "2020-06-10",
    "2020-07-29",
    "2020-09-16",
    "2020-11-05",
    "2020-12-16",
    "2021-01-27",
    "2021-03-17",
    "2021-04-28",
    "2021-06-16",
    "2021-07-28",
    "2021-09-22",
    "2021-11-03",
    "2021-12-15",
    "2022-01-26",
    "2022-03-16",
    "2022-05-04",
    "2022-06-15",
    "2022-07-27",
    "2022-09-21",
    "2022-11-02",
    "2022-12-14",
    "2023-02-01",
    "2023-03-22",
    "2023-05-03",
    "2023-06-14",
    "2023-07-26",
    "2023-09-20",
    "2023-11-01",
    "2023-12-13",
    "2024-01-31",
    "2024-03-20",
    "2024-05-01",
    "2024-06-12",
    "2024-07-31",
    "2024-09-18",
    "2024-11-07",
    "2024-12-18",
    "2025-01-29",
    "2025-03-19",
    "2025-05-07",
    "2025-06-18",
    "2025-07-30",
    "2025-09-17",
    "2025-10-29",
    "2025-12-17",
    "2026-01-28",
    "2026-03-18",
    "2026-04-29",
    "2026-06-17",
    "2026-07-29",
    "2026-09-16",
    "2026-10-28",
    "2026-12-16",
]

CPI_DATES = [
    "2020-01-14",
    "2020-02-13",
    "2020-03-11",
    "2020-04-10",
    "2020-05-12",
    "2020-06-10",
    "2020-07-14",
    "2020-08-12",
    "2020-09-11",
    "2020-10-13",
    "2020-11-12",
    "2020-12-10",
    "2021-01-13",
    "2021-02-10",
    "2021-03-10",
    "2021-04-13",
    "2021-05-12",
    "2021-06-10",
    "2021-07-13",
    "2021-08-11",
    "2021-09-14",
    "2021-10-13",
    "2021-11-10",
    "2021-12-10",
    "2022-01-12",
    "2022-02-10",
    "2022-03-10",
    "2022-04-12",
    "2022-05-11",
    "2022-06-10",
    "2022-07-13",
    "2022-08-10",
    "2022-09-13",
    "2022-10-13",
    "2022-11-10",
    "2022-12-13",
    "2023-01-12",
    "2023-02-14",
    "2023-03-14",
    "2023-04-12",
    "2023-05-10",
    "2023-06-13",
    "2023-07-12",
    "2023-08-10",
    "2023-09-13",
    "2023-10-12",
    "2023-11-14",
    "2023-12-12",
    "2024-01-11",
    "2024-02-13",
    "2024-03-12",
    "2024-04-10",
    "2024-05-15",
    "2024-06-12",
    "2024-07-11",
    "2024-08-14",
    "2024-09-11",
    "2024-10-10",
    "2024-11-13",
    "2024-12-11",
    "2025-01-15",
    "2025-02-12",
    "2025-03-12",
    "2025-04-10",
    "2025-05-13",
    "2025-06-11",
    "2025-07-15",
    "2025-08-12",
    "2025-09-10",
    "2025-10-14",
    "2025-11-12",
    "2025-12-10",
    "2026-01-14",
    "2026-02-11",
    "2026-03-11",
    "2026-04-14",
    "2026-05-13",
    "2026-06-10",
    "2026-07-14",
    "2026-08-12",
    "2026-09-10",
    "2026-10-14",
    "2026-11-10",
    "2026-12-10",
]


class EventFilter:
    """Filter trades around high-impact economic events."""

    def __init__(self, exclusion_hours: int = 48):
        self.exclusion_hours = exclusion_hours
        self._event_datetimes: list[datetime] = []

        for date_str in FOMC_DATES + CPI_DATES:
            try:
                dt = datetime.strptime(date_str, "%Y-%m-%d").replace(tzinfo=UTC)
                self._event_datetimes.append(dt)
            except ValueError:
                continue

        self._event_datetimes.sort()

    def is_excluded(self, dt: datetime) -> bool:
        """Check if datetime falls within exclusion window of any event."""
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=UTC)

        window = timedelta(hours=self.exclusion_hours)

        return any(abs((dt - event_dt).total_seconds()) < window.total_seconds() for event_dt in self._event_datetimes)


class RollingOLS:
    """Rolling OLS regression: Gold_ret = α + β1·DXY_ret + β2·ΔDFII10 + ε

    No look-ahead: coefficients estimated on data through t-1 only.
    """

    def __init__(self, window: int = 60, z_window: int = 20):
        self.window = window
        self.z_window = z_window
        self._gold_returns: list[float] = []
        self._dxy_returns: list[float] = []
        self._dfii_changes: list[float] = []
        self._residuals: list[float] = []

    def update(
        self,
        gold_ret: float,
        dxy_ret: float,
        dfii_change: float,
    ) -> float | None:
        """Add new observation, return residual z-score or None if insufficient data."""
        self._gold_returns.append(gold_ret)
        self._dxy_returns.append(dxy_ret)
        self._dfii_changes.append(dfii_change)

        if len(self._gold_returns) < self.window + 1:
            return None

        # Fit OLS on data through t-1 (no look-ahead)
        y = np.array(self._gold_returns[-(self.window + 1) : -1])
        x1 = np.array(self._dxy_returns[-(self.window + 1) : -1])
        x2 = np.array(self._dfii_changes[-(self.window + 1) : -1])

        # Design matrix: [1, x1, x2]
        design = np.column_stack([np.ones(len(y)), x1, x2])

        try:
            # OLS: β = (X'X)^-1 X'y
            beta = np.linalg.lstsq(design, y, rcond=None)[0]
        except np.linalg.LinAlgError:
            return None

        # Predict current gold return
        predicted = beta[0] + beta[1] * dxy_ret + beta[2] * dfii_change
        residual = gold_ret - predicted
        self._residuals.append(residual)

        if len(self._residuals) < self.z_window:
            return None

        # Z-score of recent residuals
        recent = self._residuals[-self.z_window :]
        mean = np.mean(recent)
        std = np.std(recent, ddof=1)

        if std < 1e-10:
            return 0.0

        z = (residual - mean) / std
        return float(z)


@dataclass
class RYDCBacktestResult:
    """Results from a single RYDC backtest run."""

    total_trades: int = 0
    winning_trades: int = 0
    losing_trades: int = 0
    win_rate: float = 0.0
    total_pnl_pct: float = 0.0
    avg_win_pct: float = 0.0
    avg_loss_pct: float = 0.0
    profit_factor: float = 0.0
    sharpe_ratio: float = 0.0
    max_drawdown_pct: float = 0.0
    trade_returns: list[float] = field(default_factory=list)
    equity_curve: list[float] = field(default_factory=list)


@dataclass
class ValidationResult:
    """Complete validation result with all gate checks."""

    hypothesis_name: str = "RYDC"
    trial_number: int = 1001  # Cumulative from Search #1

    # Gate results
    p_value: float = 1.0
    wfa_oos_positive: float = 0.0
    wfe: float = 0.0
    deflated_sharpe: float = -999.0
    pbo: float = 1.0
    bootstrap_ci_lower: float = -999.0
    bootstrap_ci_upper: float = -999.0
    min_trades: int = 0

    # Gate status
    gate_p_value: str = "FAIL"
    gate_wfa: str = "FAIL"
    gate_wfe: str = "FAIL"
    gate_dsr: str = "FAIL"
    gate_pbo: str = "FAIL"
    gate_bootstrap: str = "FAIL"
    gate_trades: str = "FAIL"

    # Overall
    overall: str = "FAIL"
    pass_count: int = 0
    fail_count: int = 0

    def check_gates(self, min_trades_threshold: int = 100):
        """Check all gates and compute overall result."""
        self.gate_p_value = "PASS" if self.p_value < 0.05 else "FAIL"

        # Handle NaN values
        if np.isnan(self.wfa_oos_positive):
            self.gate_wfa = "INSUFFICIENT_DATA"
        else:
            self.gate_wfa = "PASS" if self.wfa_oos_positive >= 0.7 else "FAIL"

        if np.isnan(self.wfe):
            self.gate_wfe = "INSUFFICIENT_DATA"
        elif self.wfe > 1.5:
            # BUG FIX (2026-07-12): WFE > 1.0 means OOS "beat" IS, which is
            # implausible as a genuine robustness signal — it's almost
            # always small-sample noise (Sharpe averaged over folds with as
            # few as min_trades_for_sharpe=10 trades is highly unstable).
            self.gate_wfe = "INSUFFICIENT_DATA"
        else:
            self.gate_wfe = "PASS" if self.wfe >= 0.5 else "FAIL"

        if np.isnan(self.deflated_sharpe):
            self.gate_dsr = "INSUFFICIENT_DATA"
        else:
            # BUG FIX (2026-07-12): DSR is P(genuine skill | data, deflated
            # for n_trials). Gating on ">0" passes almost any input, since
            # the CDF is bounded below by 0 and essentially never lands
            # exactly on it. Convention (Bailey & Lopez de Prado) is a
            # one-sided ~95% confidence threshold, matching the p<0.05 gate.
            self.gate_dsr = "PASS" if self.deflated_sharpe > 0.95 else "FAIL"

        if np.isnan(self.pbo):
            self.gate_pbo = "INSUFFICIENT_DATA"
        else:
            self.gate_pbo = "PASS" if self.pbo < 0.5 else "FAIL"

        self.gate_bootstrap = "PASS" if self.bootstrap_ci_lower > 0 else "FAIL"
        self.gate_trades = "PASS" if self.min_trades >= min_trades_threshold else "FAIL"

        # Count only PASS/FAIL (not INSUFFICIENT_DATA)
        gate_statuses = [
            self.gate_p_value,
            self.gate_wfa,
            self.gate_wfe,
            self.gate_dsr,
            self.gate_pbo,
            self.gate_bootstrap,
            self.gate_trades,
        ]
        self.pass_count = sum(1 for g in gate_statuses if g == "PASS")
        self.fail_count = sum(1 for g in gate_statuses if g == "FAIL")
        insufficient_count = sum(1 for g in gate_statuses if g == "INSUFFICIENT_DATA")

        # Overall: PASS only if all gates PASS (no FAIL, no INSUFFICIENT_DATA)
        self.overall = "PASS" if self.fail_count == 0 and insufficient_count == 0 else "FAIL"


def load_data(filepath: Path) -> list[dict]:
    """Load RYDC daily data from CSV."""
    rows = []
    with open(filepath, encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            rows.append(
                {
                    "date": row["date"],
                    "xau_close": float(row["xau_close"]),
                    "xau_high": float(row["xau_high"]),
                    "xau_low": float(row["xau_low"]),
                    "dxy_close": float(row["dxy_close"]),
                    "dfii10": float(row["dfii10"]),
                }
            )
    return rows


def run_rydc_backtest(
    data: list[dict],
    config: RYDCConfig,
    event_filter: EventFilter,
    start_idx: int = 0,
    end_idx: int | None = None,
) -> RYDCBacktestResult:
    """Run RYDC backtest on a data slice."""
    if end_idx is None:
        end_idx = len(data)

    require_cost_calibrated(RYDC_SYMBOL, mode="paper")
    round_trip_cost_pct = get_round_trip_cost_bps(RYDC_SYMBOL) / 10000.0

    ols = RollingOLS(window=config.ols_window, z_window=config.z_window)
    result = RYDCBacktestResult()

    hold_counter = 0
    entry_price = 0.0
    stop_loss = 0.0
    take_profit = 0.0
    position_type = None  # "long" or "short"

    for i in range(start_idx, end_idx):
        row = data[i]

        # Check event exclusion
        dt = datetime.strptime(row["date"], "%Y-%m-%d").replace(tzinfo=UTC)
        if event_filter.is_excluded(dt):
            continue

        # Compute returns
        if i == 0:
            continue

        gold_ret = (row["xau_close"] / data[i - 1]["xau_close"]) - 1.0
        dxy_ret = (row["dxy_close"] / data[i - 1]["dxy_close"]) - 1.0
        dfii_change = row["dfii10"] - data[i - 1]["dfii10"]

        # Update OLS
        z_score = ols.update(gold_ret, dxy_ret, dfii_change)

        if z_score is None:
            continue

        # Check position exit — stop-loss/take-profit take priority over the
        # time-based exit. Levels are pre-registered: SL = 1.5 × ATR(14),
        # TP = 2 × SL distance (see RYDCConfig and module docstring).
        if hold_counter > 0:
            hold_counter -= 1
            exit_price = None

            # Conservative ordering: stop-loss first (worst case if both
            # levels are crossed on the same bar).
            if position_type == "long":
                if row["xau_low"] <= stop_loss:
                    exit_price = stop_loss
                elif row["xau_high"] >= take_profit:
                    exit_price = take_profit
            elif position_type == "short":
                if row["xau_high"] >= stop_loss:
                    exit_price = stop_loss
                elif row["xau_low"] <= take_profit:
                    exit_price = take_profit

            if exit_price is None and hold_counter == 0:
                exit_price = row["xau_close"]

            if exit_price is not None:
                # Exit trade
                if position_type == "long":
                    pnl_pct = (exit_price - entry_price) / entry_price
                else:
                    pnl_pct = (entry_price - exit_price) / entry_price
                pnl_pct -= round_trip_cost_pct

                result.trade_returns.append(pnl_pct)
                result.total_trades += 1

                if pnl_pct > 0:
                    result.winning_trades += 1
                    result.avg_win_pct += pnl_pct
                else:
                    result.losing_trades += 1
                    result.avg_loss_pct += pnl_pct

                position_type = None
                hold_counter = 0  # SL/TP exit ends the position; no phantom time-exit later
            continue

        # Compute ATR
        atr_window = min(config.atr_period, i)
        highs = [data[j]["xau_high"] for j in range(max(0, i - atr_window), i)]
        lows = [data[j]["xau_low"] for j in range(max(0, i - atr_window), i)]
        closes = [data[j]["xau_close"] for j in range(max(0, i - atr_window), i)]

        if len(closes) < 2:
            continue

        tr_values = []
        for j in range(1, len(closes)):
            tr = max(
                highs[j] - lows[j],
                abs(highs[j] - closes[j - 1]),
                abs(lows[j] - closes[j - 1]),
            )
            tr_values.append(tr)

        atr = sum(tr_values) / len(tr_values) if tr_values else 0.0
        if atr <= 0:
            continue

        # Entry signals
        if z_score > config.z_entry:
            # Long entry
            entry_price = row["xau_close"]
            stop_loss = entry_price - (atr * config.atr_multiplier)
            take_profit = entry_price + (atr * config.atr_multiplier * 2)
            hold_counter = config.hold_days
            position_type = "long"

        elif z_score < -config.z_entry:
            # Short entry
            entry_price = row["xau_close"]
            stop_loss = entry_price + (atr * config.atr_multiplier)
            take_profit = entry_price - (atr * config.atr_multiplier * 2)
            hold_counter = config.hold_days
            position_type = "short"

    # Compute final metrics
    if result.total_trades > 0:
        result.win_rate = result.winning_trades / result.total_trades
        if result.winning_trades > 0:
            result.avg_win_pct /= result.winning_trades
        if result.losing_trades > 0:
            result.avg_loss_pct /= result.losing_trades

        # Total PnL
        result.total_pnl_pct = sum(result.trade_returns)

        total_win = sum(r for r in result.trade_returns if r > 0)
        total_loss = abs(sum(r for r in result.trade_returns if r < 0))
        result.profit_factor = total_win / total_loss if total_loss > 0 else float("inf")

        # Sharpe ratio (annualized)
        if len(result.trade_returns) > 1:
            mean_ret = np.mean(result.trade_returns)
            std_ret = np.std(result.trade_returns, ddof=1)
            # Annualize assuming ~252 trading days / 4 day hold = ~63 trades/year
            result.sharpe_ratio = (mean_ret / std_ret) * np.sqrt(63) if std_ret > 0 else 0.0

        # Max drawdown
        equity = 1.0
        peak = 1.0
        max_dd = 0.0
        for ret in result.trade_returns:
            equity *= 1 + ret
            peak = max(peak, equity)
            dd = (peak - equity) / peak
            max_dd = max(max_dd, dd)
        result.max_drawdown_pct = max_dd

    return result


def run_wfa(
    data: list[dict],
    config: RYDCConfig,
    event_filter: EventFilter,
    n_folds: int = 5,
) -> tuple[float, float, list[RYDCBacktestResult]]:
    """Run Walk-Forward Analysis and return OOS positive ratio and WFE."""
    fold_size = len(data) // (n_folds + 1)
    oos_results = []
    is_sharpes = []
    oos_sharpes = []

    for fold in range(n_folds):
        is_start = fold * fold_size
        is_end = is_start + fold_size
        oos_start = is_end
        oos_end = min(oos_start + fold_size, len(data))

        if oos_end <= oos_start:
            continue

        # IS run (for WFE calculation)
        is_result = run_rydc_backtest(data, config, event_filter, is_start, is_end)
        is_sharpes.append(is_result.sharpe_ratio)

        # OOS run
        oos_result = run_rydc_backtest(data, config, event_filter, oos_start, oos_end)
        oos_results.append(oos_result)
        oos_sharpes.append(oos_result.sharpe_ratio)

    # OOS positive ratio
    oos_positive = sum(1 for r in oos_results if r.total_pnl_pct > 0)
    oos_ratio = oos_positive / len(oos_results) if oos_results else 0.0

    # WFA: average OOS Sharpe / average IS Sharpe
    # Only use folds with enough trades for reliable Sharpe
    min_trades_for_sharpe = 10
    valid_is = [s for s, r in zip(is_sharpes, oos_results, strict=False) if r.total_trades >= min_trades_for_sharpe]
    valid_oos = [s for s, r in zip(oos_sharpes, oos_results, strict=False) if r.total_trades >= min_trades_for_sharpe]

    if valid_is and valid_oos:
        avg_is = float(np.mean(valid_is))
        avg_oos = float(np.mean(valid_oos))
        wfe = avg_oos / avg_is if avg_is > 0 else 0.0
    else:
        wfe = float("nan")

    return oos_ratio, wfe, oos_results


def compute_deflated_sharpe(
    sharpe: float,
    n_trials: int,
    n_observations: int,
    skewness: float = 0.0,
    kurtosis: float = 3.0,
) -> float:
    """Compute Deflated Sharpe Ratio (Bailey & López de Prado 2014).

    Accounts for multiple testing bias.
    Returns NaN if n_observations is too small for reliable estimation.
    """
    from scipy import stats

    # Guard: need minimum observations for reliable estimate
    if n_observations < 30:
        return float("nan")

    # Sharpe ratio standard error (also used to scale the expected-max term below)
    sr_se = np.sqrt((1 - skewness * sharpe + (kurtosis - 1) / 4 * sharpe**2) / (n_observations - 1))

    # Guard: sr_se too small
    if sr_se < 1e-10:
        return float("nan")

    # Expected maximum Sharpe under null (no skill).
    # BUG FIX (2026-07-12): this must be scaled by sr_se — the expected max
    # of N draws has to be in the same units as the observed Sharpe. Left
    # unscaled, e_max_sharpe was ~3.26 regardless of this trial's own
    # sampling noise, which silently forced DSR toward numerical zero
    # (e.g. 1.4e-116) for almost any realistic input instead of reflecting
    # the actual deflation for this sample size.
    euler_mascheroni = 0.5772
    e_max_sharpe = sr_se * (
        (1 - euler_mascheroni) * stats.norm.ppf(1 - 1 / n_trials)
        + euler_mascheroni * stats.norm.ppf(1 - 1 / (n_trials * np.e))
    )

    # Deflated Sharpe
    dsr = stats.norm.cdf((sharpe - e_max_sharpe) / sr_se)
    return dsr


def bootstrap_sharpe_ci(
    returns: list[float],
    n_bootstrap: int = 1000,
    block_size: int = 4,
    confidence: float = 0.95,
) -> tuple[float, float]:
    """Compute bootstrap confidence interval for Sharpe ratio.

    Uses block bootstrap to preserve autocorrelation structure.
    """
    returns_arr = np.array(returns)
    n = len(returns_arr)

    if n < block_size:
        return -999.0, -999.0

    sharpes = []
    for _ in range(n_bootstrap):
        # Block bootstrap
        blocks: list[float] = []
        while len(blocks) < n:
            start = np.random.randint(0, n - block_size + 1)
            blocks.extend(returns_arr[start : start + block_size])
        sample = np.array(blocks[:n])

        # Compute Sharpe
        mean_ret = np.mean(sample)
        std_ret = np.std(sample, ddof=1)
        if std_ret > 0:
            sharpes.append(mean_ret / std_ret * np.sqrt(63))  # Annualize

    if not sharpes:
        return -999.0, -999.0

    # Percentile CI
    alpha = 1 - confidence
    lower = np.percentile(sharpes, alpha / 2 * 100)
    upper = np.percentile(sharpes, (1 - alpha / 2) * 100)

    return float(lower), float(upper)


def main():
    parser = argparse.ArgumentParser(description="Run RYDC validation")
    parser.add_argument(
        "--data", type=str, default=None, help="Path to RYDC daily CSV (default: data/rydc/rydc_daily.csv)"
    )
    parser.add_argument("--folds", type=int, default=5, help="Number of WFA folds (default: 5)")
    parser.add_argument("--bootstrap", type=int, default=1000, help="Number of bootstrap samples (default: 1000)")
    parser.add_argument("--verbose", action="store_true", help="Verbose output")
    args = parser.parse_args()

    # Load data
    data_path = Path(args.data) if args.data else PROJECT_ROOT / "data" / "rydc" / "rydc_daily.csv"
    if not data_path.exists():
        print(f"ERROR: Data file not found: {data_path}")
        print("Run: python scripts/prepare_rydc_data.py first")
        sys.exit(1)

    print("=" * 60)
    print("RYDC Validation Pipeline")
    print("=" * 60)
    print(f"Data: {data_path}")

    data = load_data(data_path)
    print(f"Rows: {len(data)} ({data[0]['date']} -> {data[-1]['date']})")

    # Pre-registered config (frozen)
    config = RYDCConfig()
    event_filter = EventFilter(exclusion_hours=config.event_exclusion_hours)

    print("\nPre-registered parameters:")
    print(f"  OLS window: {config.ols_window} days")
    print(f"  Z-score threshold: {config.z_entry}")
    print(f"  Hold period: {config.hold_days} days")
    print(f"  Stop-loss: {config.atr_multiplier} x ATR({config.atr_period})")
    print(f"  Event exclusion: {config.event_exclusion_hours}h")
    print("  Trial number: 1001+ (cumulative from Search #1)")

    # Split data: 60% IS, 40% OOS (pre-registered)
    split_idx = int(len(data) * 0.6)
    is_data = data[:split_idx]
    oos_data = data[split_idx:]

    print("\nData split:")
    print(f"  IS:  {is_data[0]['date']} -> {is_data[-1]['date']} ({len(is_data)} rows)")
    print(f"  OOS: {oos_data[0]['date']} -> {oos_data[-1]['date']} ({len(oos_data)} rows)")

    # Run full backtest on OOS
    print("\n" + "=" * 60)
    print("Running OOS backtest...")
    oos_result = run_rydc_backtest(oos_data, config, event_filter)

    print("\nOOS Results:")
    print(f"  Total trades: {oos_result.total_trades}")
    print(f"  Win rate: {oos_result.win_rate:.2%}")
    print(f"  Profit factor: {oos_result.profit_factor:.2f}")
    print(f"  Sharpe ratio: {oos_result.sharpe_ratio:.3f}")
    print(f"  Max drawdown: {oos_result.max_drawdown_pct:.2%}")

    # Statistical significance (t-test on trade returns)
    if oos_result.trade_returns:
        from scipy import stats

        t_stat, p_value = stats.ttest_1samp(oos_result.trade_returns, 0)
        print(f"  t-statistic: {t_stat:.3f}")
        print(f"  p-value: {p_value:.4f}")
    else:
        t_stat, p_value = 0.0, 1.0

    # Walk-Forward Analysis
    print("\n" + "=" * 60)
    print(f"Running WFA ({args.folds} folds)...")
    wfa_oos_ratio, wfe, wfa_results = run_wfa(data, config, event_filter, args.folds)

    # Debug WFA details
    print("\n  WFA Debug:")
    for i, r in enumerate(wfa_results):
        print(f"    Fold {i}: trades={r.total_trades}, sharpe={r.sharpe_ratio:.4f}, pnl={r.total_pnl_pct:.4%}")
    print(f"  OOS positive ratio: {wfa_oos_ratio:.2%}")
    print(f"  Walk-Forward Efficiency: {wfe:.3f}")
    if wfe > 1.0:
        print("  WARNING: WFE > 1.0 is suspicious (OOS > IS)")

    # Deflated Sharpe Ratio
    print("\n" + "=" * 60)
    print("Computing Deflated Sharpe Ratio...")
    print(f"  Input: sharpe={oos_result.sharpe_ratio:.4f}, n_trials=1001, n_obs={len(oos_result.trade_returns)}")
    dsr = compute_deflated_sharpe(
        sharpe=oos_result.sharpe_ratio,
        n_trials=1001,  # Cumulative trial count
        n_observations=len(oos_result.trade_returns),
    )
    # BUG FIX (2026-07-12): DSR is a CDF value (0-1 probability), not a
    # raw score. Display with appropriate precision.
    if np.isnan(dsr):
        print(f"  DSR: NaN (n={len(oos_result.trade_returns)} < 30 minimum)")
    else:
        print(f"  DSR: {dsr:.6f} (threshold: > 0.95 for 95% confidence)")
    if dsr == 0.0 and len(oos_result.trade_returns) < 100:
        print(f"  WARNING: DSR=0.0 with n={len(oos_result.trade_returns)} < 100 — may be invalid")

    # Bootstrap Sharpe CI
    print("\n" + "=" * 60)
    print(f"Running bootstrap ({args.bootstrap} samples)...")
    ci_lower, ci_upper = bootstrap_sharpe_ci(
        oos_result.trade_returns,
        n_bootstrap=args.bootstrap,
        block_size=config.hold_days,
    )
    print(f"  95% CI: [{ci_lower:.3f}, {ci_upper:.3f}]")

    # BUG FIX (2026-07-12): "PBO = 1 - WFE" is not PBO. Real CSCV-based PBO
    # (Bailey, Borwein, Lopez de Prado & Zhu 2015) measures the probability
    # that the BEST of many candidate parameterizations, selected in-sample,
    # underperforms out-of-sample — it quantifies selection/overfitting
    # bias from a search. RYDC Arm A is a single frozen configuration
    # (pre-registration §8: no in-sample selection happened). There is no
    # selection step here for PBO to measure, and deriving it algebraically
    # from WFE just makes it 100% collinear with an already-unreliable
    # metric rather than an independent check. Marking N/A honestly rather
    # than reporting a number that looks like independent evidence but isn't.
    pbo = float("nan")
    print(
        "  PBO: N/A — single frozen configuration, no in-sample "
        "selection to measure (CSCV PBO applies to Search #1's "
        "1000+-combo scan, not to a pre-registered single hypothesis)"
    )

    # Validation result
    validation = ValidationResult(
        p_value=p_value,
        wfa_oos_positive=wfa_oos_ratio,
        wfe=wfe,
        deflated_sharpe=dsr,
        pbo=pbo,
        bootstrap_ci_lower=ci_lower,
        bootstrap_ci_upper=ci_upper,
        min_trades=oos_result.total_trades,
    )
    validation.check_gates()

    # Print validation report
    print("\n" + "=" * 60)
    print("VALIDATION REPORT")
    print("=" * 60)
    print(f"Hypothesis: {validation.hypothesis_name}")
    print(f"Trial #: {validation.trial_number}")
    print()
    print(f"{'Gate':<30} {'Value':>15} {'Threshold':>15} {'Status':>8}")
    print("-" * 70)
    print(f"{'p-value':<30} {validation.p_value:>15.4f} {'< 0.05':>15} {validation.gate_p_value:>8}")
    print(f"{'WFA OOS positive':<30} {validation.wfa_oos_positive:>15.2%} {'>= 70%':>15} {validation.gate_wfa:>8}")
    print(f"{'WFE':<30} {validation.wfe:>15.4f} {'>= 0.5 & < 1.5':>15} {validation.gate_wfe:>8}")
    # BUG FIX (2026-07-12): DSR is P(genuine skill), display as percentage
    if np.isnan(validation.deflated_sharpe):
        print(f"{'Deflated Sharpe':<30} {'NaN':>15} {'> 95%':>15} {validation.gate_dsr:>8}")
    else:
        print(
            f"{'Deflated Sharpe':<30} {validation.deflated_sharpe * 100:>14.2f}% {'> 95%':>15} {validation.gate_dsr:>8}"
        )
    # BUG FIX (2026-07-12): PBO is N/A for single frozen config
    if np.isnan(validation.pbo):
        print(f"{'PBO':<30} {'N/A':>15} {'N/A':>15} {validation.gate_pbo:>8}")
    else:
        print(f"{'PBO':<30} {validation.pbo:>15.4f} {'< 0.5':>15} {validation.gate_pbo:>8}")
    print(
        f"{'Bootstrap CI lower':<30} {validation.bootstrap_ci_lower:>15.4f} {'> 0':>15} {validation.gate_bootstrap:>8}"
    )
    print(f"{'Min trades':<30} {validation.min_trades:>15d} {'>= 100':>15} {validation.gate_trades:>8}")
    print("-" * 70)
    print(f"{'PASS / TOTAL':<30} {validation.pass_count:>15d} / {validation.fail_count + validation.pass_count}")
    print(f"\n{'OVERALL':<30} {validation.overall:>15}")

    # Save result
    output_dir = PROJECT_ROOT / "reports" / "validation"
    output_dir.mkdir(parents=True, exist_ok=True)
    output_file = output_dir / f"rydc_validation_{datetime.now():%Y%m%d_%H%M%S}.json"

    result_dict = {
        "hypothesis": "RYDC",
        "trial_number": 1001,
        "timestamp": datetime.now(UTC).isoformat(),
        "data_path": str(data_path),
        "config": {
            "ols_window": config.ols_window,
            "z_entry": config.z_entry,
            "hold_days": config.hold_days,
            "atr_multiplier": config.atr_multiplier,
            "atr_period": config.atr_period,
            "event_exclusion_hours": config.event_exclusion_hours,
        },
        "oos_results": {
            "total_trades": oos_result.total_trades,
            "win_rate": oos_result.win_rate,
            "profit_factor": oos_result.profit_factor,
            "sharpe_ratio": oos_result.sharpe_ratio,
            "max_drawdown_pct": oos_result.max_drawdown_pct,
            "t_statistic": t_stat,
            "p_value": p_value,
        },
        "gates": {
            "p_value": {"value": p_value, "threshold": 0.05, "status": validation.gate_p_value},
            "wfa_oos_positive": {"value": wfa_oos_ratio, "threshold": 0.7, "status": validation.gate_wfa},
            "wfe": {"value": wfe, "threshold": ">= 0.5 & < 1.5", "status": validation.gate_wfe},
            "deflated_sharpe": {"value": dsr, "threshold": 0.95, "status": validation.gate_dsr},
            "pbo": {"value": pbo, "threshold": "N/A (single config)", "status": validation.gate_pbo},
            "bootstrap_ci_lower": {"value": ci_lower, "threshold": 0.0, "status": validation.gate_bootstrap},
            "min_trades": {"value": oos_result.total_trades, "threshold": 100, "status": validation.gate_trades},
        },
        "overall": validation.overall,
        "pass_count": validation.pass_count,
        "fail_count": validation.fail_count,
    }

    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(result_dict, f, indent=2, default=str)

    print(f"\nSaved to: {output_file}")


if __name__ == "__main__":
    main()
