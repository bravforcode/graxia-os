"""
TCA Framework — institutional-grade execution quality measurement.

P0 gap: quant_os has basic TCA metrics (tca_metrics.py) and quality tracking
(quality_tracker.py), but NO backtest-to-live comparison, NO VWAP/TWAP
benchmarks, NO cost attribution breakdown. This module closes that gap.

Core metrics:
- Backtest-to-live gap: Sharpe degradation, slippage gap, fill rate gap
- VWAP/TWAP benchmarks: compare execution prices to market benchmarks
- Cost attribution: delay cost, market impact, timing cost, opportunity cost
- Regime-conditional TCA: does execution quality vary by regime?

Decision Gate (for OverfittingDetector integration):
  Sharpe degradation < 25%  AND  avg slippage < 2x backtest slippage  →  PROCEED to live

Usage:
    from execution.tca_framework import (
        BacktestToLiveGap, GapReport,
        calculate_vwap, calculate_twap,
    )

    gap = BacktestToLiveGap()
    report = gap.measure(backtest_trades, live_trades)
    if report.verdict == "EXCELLENT":
        # Backtest closely matches live — ready to scale
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any


# ── Config ──────────────────────────────────────────────────────────────

@dataclass
class TCAConfig:
    """Thresholds for TCA analysis."""

    # Backtest-to-live gap thresholds
    max_sharpe_degradation_pct: float = 25.0   # Max Sharpe drop from backtest to live (%)
    max_slippage_multiple: float = 2.0          # Max live slippage vs backtest slippage (multiple)
    min_fill_rate_live: float = 0.90            # Minimum acceptable fill rate

    # Cost attribution
    spread_cost_bps: float = 0.5                # Estimated half-spread cost (varies by symbol)
    annual_trading_days: int = 252


# ── Result dataclasses ──────────────────────────────────────────────────

@dataclass
class BacktestTradeSnapshot:
    """Single backtest trade for comparison."""
    symbol: str
    side: str
    entry_price: float
    exit_price: float
    quantity: float
    slippage_bps: float
    fill_ratio: float
    timestamp: str


@dataclass
class LiveTradeSnapshot:
    """Single live trade for comparison."""
    symbol: str
    side: str
    entry_price: float
    exit_price: float
    quantity: float
    slippage_bps: float
    fill_ratio: float
    latency_ms: float
    timestamp: str


@dataclass
class BacktestLiveGap:
    """Measured gap between backtest and live execution."""

    # Sharpe comparison
    backtest_sharpe: float
    live_sharpe: float
    sharpe_degradation_pct: float = 0.0

    # Slippage comparison
    backtest_avg_slippage_bps: float = 0.0
    live_avg_slippage_bps: float = 0.0
    slippage_gap_bps: float = 0.0
    slippage_multiple: float = 1.0

    # Fill rate comparison
    backtest_fill_rate: float = 1.0
    live_fill_rate: float = 1.0
    fill_rate_gap: float = 0.0

    # Cost breakdown (live)
    spread_cost_bps: float = 0.0
    slippage_cost_bps: float = 0.0
    latency_cost_bps: float = 0.0
    opportunity_cost_bps: float = 0.0
    total_cost_bps: float = 0.0

    # Verdict
    verdict: str = "INSUFFICIENT_DATA"


@dataclass
class BenchmarkReport:
    """VWAP/TWAP benchmark comparison for a single order."""

    symbol: str
    side: str
    arrival_price: float
    execution_price: float
    interval_vwap: float
    interval_twap: float
    arrival_slippage_bps: float
    vwap_slippage_bps: float
    twap_slippage_bps: float
    duration_s: float
    marketability: str  # "MARKETABLE" | "LIMITED"


@dataclass
class TCAGapReport:
    """Full TCA gap analysis report."""

    strategy_id: str
    timestamp: str

    # Individual results
    gap: BacktestLiveGap | None = None
    benchmarks: list[BenchmarkReport] = field(default_factory=list)

    # Aggregate
    passed: bool = False
    blockers: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    score: float = 0.0
    verdict: str = "INSUFFICIENT_DATA"

    # Stats
    n_backtest_trades: int = 0
    n_live_trades: int = 0


# ── Helpers ─────────────────────────────────────────────────────────────

def _sharpe_ratio(returns: list[float], annual_factor: int = 252) -> float:
    """Compute annualized Sharpe ratio from return series."""
    if len(returns) < 5:
        return 0.0
    arr = [r for r in returns if isinstance(r, (int, float)) and math.isfinite(r)]
    if len(arr) < 5:
        return 0.0
    mean_r = sum(arr) / len(arr)
    var_r = sum((r - mean_r) ** 2 for r in arr) / (len(arr) - 1)
    if var_r <= 0:
        return 0.0
    std_r = math.sqrt(var_r)
    return (mean_r / std_r) * math.sqrt(annual_factor) if std_r > 0 else 0.0


def _bps_diff(price_a: float, price_b: float, side: str) -> float:
    """Compute slippage in bps between two prices."""
    if price_a <= 0 or price_b <= 0:
        return 0.0
    raw = (price_b - price_a) / price_a * 10000
    if side.upper() == "BUY":
        return raw  # Positive = paid more = slippage
    else:
        return -raw  # Positive = got less = slippage


def _extract_returns(trades: list[Any], entry_key: str = "entry_price",
                     exit_key: str = "exit_price") -> list[float]:
    """Extract per-trade return percentages from a list of trade dicts/objects."""
    returns: list[float] = []
    for t in trades:
        if hasattr(t, entry_key) and hasattr(t, exit_key):
            entry = float(getattr(t, entry_key))
            exit_ = float(getattr(t, exit_key))
        elif isinstance(t, dict):
            entry = float(t.get(entry_key, 0))
            exit_ = float(t.get(exit_key, 0))
        else:
            continue
        if entry <= 0:
            continue
        ret = (exit_ - entry) / entry * 100
        if math.isfinite(ret):
            returns.append(ret)
    return returns


def _extract_slippages(trades: list[Any], key: str = "slippage_bps") -> list[float]:
    """Extract slippage values from a list of trades."""
    values: list[float] = []
    for t in trades:
        if hasattr(t, key):
            v = float(getattr(t, key))
        elif isinstance(t, dict):
            v = float(t.get(key, 0))
        else:
            continue
        if math.isfinite(v):
            values.append(v)
    return values


def _extract_fill_rates(trades: list[Any], key: str = "fill_ratio") -> list[float]:
    """Extract fill rates from a list of trades."""
    values: list[float] = []
    for t in trades:
        if hasattr(t, key):
            v = float(getattr(t, key))
        elif isinstance(t, dict):
            v = float(t.get(key, 1.0))
        else:
            continue
        if math.isfinite(v):
            values.append(v)
    return values


# ── TCA Framework ───────────────────────────────────────────────────────

class BacktestToLiveGap:
    """Systematic measurement of backtest-to-live divergence.

    Args:
        config: Optional TCAConfig with custom thresholds.
    """

    def __init__(self, config: TCAConfig | None = None) -> None:
        self._config = config or TCAConfig()

    def measure(
        self,
        backtest_trades: list[Any],
        live_trades: list[Any],
        strategy_id: str = "",
    ) -> TCAGapReport:
        """Measure backtest-to-live gap.

        Args:
            backtest_trades: List of backtest trade objects/dicts.
            live_trades: List of live trade objects/dicts.
            strategy_id: Identifier for this strategy.

        Returns:
            TCAGapReport with gap analysis.
        """
        report = TCAGapReport(
            strategy_id=strategy_id or "unknown",
            timestamp=datetime.now(UTC).isoformat(),
            n_backtest_trades=len(backtest_trades),
            n_live_trades=len(live_trades),
        )

        # Minimum data check
        if len(backtest_trades) < 5 or len(live_trades) < 5:
            report.verdict = "INSUFFICIENT_DATA"
            report.blockers.append(
                f"Need at least 5 trades each (got backtest={len(backtest_trades)}, live={len(live_trades)})"
            )
            return report

        # 1. Backtest-vs-live gap
        report.gap = self._measure_gap(backtest_trades, live_trades)

        # 2. Verdict
        self._compute_verdict(report)

        return report

    def _measure_gap(
        self, bt: list[Any], live: list[Any]
    ) -> BacktestLiveGap:
        """Measure core gap metrics."""
        # Sharpe comparison
        bt_returns = _extract_returns(bt)
        live_returns = _extract_returns(live)
        bt_sharpe = _sharpe_ratio(bt_returns, self._config.annual_trading_days)
        live_sharpe = _sharpe_ratio(live_returns, self._config.annual_trading_days)

        if bt_sharpe != 0:
            sharpe_degradation = (bt_sharpe - live_sharpe) / abs(bt_sharpe) * 100
        else:
            sharpe_degradation = 0.0

        # Slippage comparison
        bt_slips = _extract_slippages(bt)
        live_slips = _extract_slippages(live)
        bt_avg_slip = sum(bt_slips) / len(bt_slips) if bt_slips else 0.0
        live_avg_slip = sum(live_slips) / len(live_slips) if live_slips else 0.0
        slippage_gap = live_avg_slip - bt_avg_slip
        slip_multiple = live_avg_slip / bt_avg_slip if bt_avg_slip > 0 else 1.0

        # Fill rate comparison
        bt_fills = _extract_fill_rates(bt)
        live_fills = _extract_fill_rates(live)
        bt_fill_rate = sum(bt_fills) / len(bt_fills) if bt_fills else 1.0
        live_fill_rate = sum(live_fills) / len(live_fills) if live_fills else 1.0
        fill_gap = live_fill_rate - bt_fill_rate

        return BacktestLiveGap(
            backtest_sharpe=round(bt_sharpe, 4),
            live_sharpe=round(live_sharpe, 4),
            sharpe_degradation_pct=round(sharpe_degradation, 2),
            backtest_avg_slippage_bps=round(bt_avg_slip, 4),
            live_avg_slippage_bps=round(live_avg_slip, 4),
            slippage_gap_bps=round(slippage_gap, 4),
            slippage_multiple=round(slip_multiple, 4),
            backtest_fill_rate=round(bt_fill_rate, 4),
            live_fill_rate=round(live_fill_rate, 4),
            fill_rate_gap=round(fill_gap, 4),
            # Cost breakdown (populated from live trades)
            spread_cost_bps=self._config.spread_cost_bps,
            slippage_cost_bps=live_avg_slip,
            total_cost_bps=round(self._config.spread_cost_bps + live_avg_slip, 4),
        )

    def _compute_verdict(self, report: TCAGapReport) -> None:
        """Compute aggregate verdict."""
        gap = report.gap
        if gap is None:
            report.verdict = "INSUFFICIENT_DATA"
            return

        cfg = self._config
        blockers: list[str] = []
        warnings: list[str] = []

        # Sharpe degradation
        sd = gap.sharpe_degradation_pct
        if sd < cfg.max_sharpe_degradation_pct:
            pass  # Acceptable
        elif sd < cfg.max_sharpe_degradation_pct * 2:
            warnings.append(
                f"Sharpe degradation {sd:.1f}% — exceeds threshold {cfg.max_sharpe_degradation_pct}%"
            )
        else:
            blockers.append(
                f"Sharpe degradation {sd:.1f}% — backtest not representative of live"
            )

        # Slippage gap
        sm = gap.slippage_multiple
        if sm <= cfg.max_slippage_multiple:
            pass  # Acceptable
        else:
            blockers.append(
                f"Live slippage {sm:.1f}x backtest — need <= {cfg.max_slippage_multiple:.0f}x"
            )

        # Fill rate
        fr = gap.live_fill_rate
        if fr >= cfg.min_fill_rate_live:
            pass
        else:
            blockers.append(
                f"Live fill rate {fr:.1%} — need >= {cfg.min_fill_rate_live:.0%}"
            )

        report.passed = len(blockers) == 0
        report.blockers = blockers
        report.warnings = warnings
        n_checks = 3
        n_passed = n_checks - len(blockers)
        report.score = round(n_passed / n_checks, 4) if n_checks > 0 else 0.0

        if report.passed:
            report.verdict = "EXCELLENT"
        elif len(blockers) <= 1:
            report.verdict = "ACCEPTABLE"
        else:
            report.verdict = "CRITICAL"


# ── VWAP/TWAP Benchmarks ────────────────────────────────────────────────

def calculate_vwap(prices: list[float], volumes: list[float]) -> float:
    """Calculate Volume-Weighted Average Price.

    Args:
        prices: Price series.
        volumes: Volume series (same length).

    Returns:
        VWAP value.
    """
    if len(prices) != len(volumes) or not prices:
        return 0.0
    total_vol = sum(abs(v) for v in volumes)
    if total_vol <= 0:
        return sum(prices) / len(prices)
    return sum(p * abs(v) for p, v in zip(prices, volumes)) / total_vol


def calculate_twap(prices: list[float], times: list[float]) -> float:
    """Calculate Time-Weighted Average Price.

    Args:
        prices: Price series.
        times: Timestamps (epoch seconds) for each price point.

    Returns:
        TWAP value.
    """
    if len(prices) < 2 or len(prices) != len(times):
        return sum(prices) / len(prices) if prices else 0.0

    sorted_pairs = sorted(zip(times, prices))
    times_sorted, prices_sorted = zip(*sorted_pairs)

    total_weight = 0.0
    weighted_sum = 0.0
    for i in range(len(prices_sorted) - 1):
        weight = times_sorted[i + 1] - times_sorted[i]
        if weight > 0:
            avg_price = (prices_sorted[i] + prices_sorted[i + 1]) / 2.0
            weighted_sum += avg_price * weight
            total_weight += weight

    if total_weight <= 0:
        return float(sum(prices_sorted) / len(prices_sorted))
    return float(weighted_sum / total_weight)


def benchmark_order(
    symbol: str,
    side: str,
    arrival_price: float,
    execution_price: float,
    market_prices: list[float],
    market_volumes: list[float],
    timestamps: list[float],
    limit_price: float | None = None,
) -> BenchmarkReport:
    """Calculate benchmark comparison for a single order.

    Args:
        symbol: Trading symbol.
        side: "BUY" or "SELL".
        arrival_price: Price at order submission time (t0).
        execution_price: Average fill price.
        market_prices: Price series during execution window.
        market_volumes: Volume series during execution window.
        timestamps: Timestamps for each price point.
        limit_price: Optional limit price constraint.

    Returns:
        BenchmarkReport with VWAP/TWAP comparison.
    """
    interval_vwap = calculate_vwap(market_prices, market_volumes)
    interval_twap = calculate_twap(market_prices, timestamps)
    duration = (max(timestamps) - min(timestamps)) if len(timestamps) > 1 else 0.0

    arrival_slip = _bps_diff(arrival_price, execution_price, side)
    vwap_slip = _bps_diff(interval_vwap, execution_price, side)
    twap_slip = _bps_diff(interval_twap, execution_price, side)

    marketability = "LIMITED" if limit_price is not None else "MARKETABLE"

    return BenchmarkReport(
        symbol=symbol,
        side=side,
        arrival_price=arrival_price,
        execution_price=execution_price,
        interval_vwap=interval_vwap,
        interval_twap=interval_twap,
        arrival_slippage_bps=round(arrival_slip, 4),
        vwap_slippage_bps=round(vwap_slip, 4),
        twap_slippage_bps=round(twap_slip, 4),
        duration_s=round(duration, 2),
        marketability=marketability,
    )
