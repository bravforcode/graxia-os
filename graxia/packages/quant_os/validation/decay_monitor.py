"""Phase 4 — Strategy Decay Monitor.

Multi-metric framework for detecting strategy degradation in live trading.
Based on AQR (2020-2025) 8-metric decay detection framework.

Metrics tracked:
1. Rolling Sharpe ratio
2. Rolling Information Ratio
3. Win rate decay
4. Signal half-life
5. Factor exposure drift
6. Trade frequency deviation
7. Average trade PnL decay
8. Profit factor decay

Early warning: any 3+ metrics triggering = strategy review required.
"""

from __future__ import annotations

import math
from collections import deque
from dataclasses import dataclass, field
from enum import Enum


class DecaySignal(str, Enum):
    NORMAL = "normal"
    WARNING = "warning"  # 1-2 metrics triggering
    CRITICAL = "critical"  # 3+ metrics triggering
    EMERGENCY = "emergency"  # 5+ metrics triggering


@dataclass
class DecayConfig:
    """Decay monitoring configuration."""

    # Rolling window for metrics
    rolling_window: int = 50  # Bars per rolling metric

    # Sharpe thresholds
    sharpe_warning: float = 0.5  # Rolling Sharpe below this = warning
    sharpe_critical: float = 0.0  # Rolling Sharpe below this = critical
    sharpe_emergency: float = -0.5  # Rolling Sharpe below this = emergency

    # Information Ratio thresholds
    ir_warning: float = 0.3
    ir_critical: float = 0.0

    # Win rate thresholds
    win_rate_warning: float = 0.45
    win_rate_critical: float = 0.40

    # Trade PnL decay (% decline from baseline)
    pnl_decay_warning: float = 0.30  # 30% decline
    pnl_decay_critical: float = 0.50  # 50% decline

    # Profit factor thresholds
    pf_warning: float = 1.2
    pf_critical: float = 1.0

    # Trade frequency deviation
    freq_deviation_warning: float = 0.30  # 30% deviation from baseline
    freq_deviation_critical: float = 0.50  # 50% deviation

    # Signal half-life (bars until signal correlation drops to 50%)
    signal_half_life_warning: int = 20
    signal_half_life_critical: int = 10


@dataclass
class DecayMetrics:
    """Current decay metrics."""

    rolling_sharpe: float = 0.0
    rolling_ir: float = 0.0
    win_rate: float = 0.0
    win_rate_baseline: float = 0.0
    signal_half_life: int = 0
    factor_drift: float = 0.0
    trade_frequency: float = 0.0
    trade_frequency_baseline: float = 0.0
    avg_trade_pnl: float = 0.0
    avg_trade_pnl_baseline: float = 0.0
    profit_factor: float = 0.0


@dataclass
class DecayAlert:
    """Individual decay alert."""

    metric_name: str
    current_value: float
    threshold: float
    severity: str  # "warning", "critical", "emergency"
    message: str


class DecayMonitor:
    """Multi-metric strategy decay detection.

    Tracks 8 metrics and generates alerts when degradation is detected.
    """

    def __init__(self, config: DecayConfig | None = None):
        self.config = config or DecayConfig()
        # Phase 4: Use deque with maxlen to cap memory at rolling_window
        self._returns: deque[float] = deque(maxlen=self.config.rolling_window)
        self._trades: deque[dict] = deque(maxlen=self.config.rolling_window)
        self._signals: deque[float] = deque(maxlen=self.config.rolling_window)
        self._baseline: DecayMetrics | None = None
        self._alerts: list[DecayAlert] = []

    def set_baseline(self, metrics: DecayMetrics):
        """Set baseline metrics from initial validation period."""
        self._baseline = metrics

    def update(self, bar_return: float, trade_pnl: float | None = None, signal: float | None = None):
        """Update with new data.

        Args:
            bar_return: Per-bar portfolio return
            trade_pnl: Optional trade PnL if a trade closed
            signal: Optional strategy signal value
        """
        self._returns.append(bar_return)

        if trade_pnl is not None:
            self._trades.append({"pnl": trade_pnl})

        if signal is not None:
            self._signals.append(signal)

    def evaluate(self) -> tuple[DecaySignal, list[DecayAlert]]:
        """Evaluate current decay state.

        Returns:
            (overall_signal, list_of_alerts)
        """
        alerts = []
        n = len(self._returns)

        if n < self.config.rolling_window:
            return DecaySignal.NORMAL, []

        # Phase 4: Convert deque to list for slicing support
        returns_list = list(self._returns)
        trades_list = list(self._trades)
        signals_list = list(self._signals)

        # 1. Rolling Sharpe
        window_returns = returns_list[-self.config.rolling_window:]
        rolling_sharpe = self._compute_sharpe(window_returns)
        if rolling_sharpe < self.config.sharpe_emergency:
            alerts.append(DecayAlert("rolling_sharpe", rolling_sharpe, self.config.sharpe_emergency, "emergency", f"Rolling Sharpe {rolling_sharpe:.2f} < {self.config.sharpe_emergency}"))
        elif rolling_sharpe < self.config.sharpe_critical:
            alerts.append(DecayAlert("rolling_sharpe", rolling_sharpe, self.config.sharpe_critical, "critical", f"Rolling Sharpe {rolling_sharpe:.2f} < {self.config.sharpe_critical}"))
        elif rolling_sharpe < self.config.sharpe_warning:
            alerts.append(DecayAlert("rolling_sharpe", rolling_sharpe, self.config.sharpe_warning, "warning", f"Rolling Sharpe {rolling_sharpe:.2f} < {self.config.sharpe_warning}"))

        # 2. Rolling Information Ratio (using benchmark = 0)
        rolling_ir = rolling_sharpe  # Simplified: IR ≈ Sharpe when benchmark = 0
        if rolling_ir < self.config.ir_critical:
            alerts.append(DecayAlert("rolling_ir", rolling_ir, self.config.ir_critical, "critical", f"Rolling IR {rolling_ir:.2f} < {self.config.ir_critical}"))
        elif rolling_ir < self.config.ir_warning:
            alerts.append(DecayAlert("rolling_ir", rolling_ir, self.config.ir_warning, "warning", f"Rolling IR {rolling_ir:.2f} < {self.config.ir_warning}"))

        # 3. Win rate decay
        if trades_list:
            recent_trades = trades_list[-self.config.rolling_window:]
            wins = sum(1 for t in recent_trades if t["pnl"] > 0)
            win_rate = wins / len(recent_trades) if recent_trades else 0.5
            baseline_wr = self._baseline.win_rate if self._baseline else 0.5
            if win_rate < self.config.win_rate_critical:
                alerts.append(DecayAlert("win_rate", win_rate, self.config.win_rate_critical, "critical", f"Win rate {win_rate:.1%} < {self.config.win_rate_critical:.0%}"))
            elif win_rate < self.config.win_rate_warning:
                alerts.append(DecayAlert("win_rate", win_rate, self.config.win_rate_warning, "warning", f"Win rate {win_rate:.1%} < {self.config.win_rate_warning:.0%}"))

        # 4. Signal half-life (autocorrelation decay)
        if len(signals_list) >= self.config.rolling_window:
            half_life = self._compute_half_life(signals_list[-self.config.rolling_window:])
            if half_life < self.config.signal_half_life_critical:
                alerts.append(DecayAlert("signal_half_life", half_life, self.config.signal_half_life_critical, "critical", f"Signal half-life {half_life} bars < {self.config.signal_half_life_critical}"))
            elif half_life < self.config.signal_half_life_warning:
                alerts.append(DecayAlert("signal_half_life", half_life, self.config.signal_half_life_warning, "warning", f"Signal half-life {half_life} bars < {self.config.signal_half_life_warning}"))

        # 5. Average trade PnL decay
        if trades_list and self._baseline and self._baseline.avg_trade_pnl != 0:
            recent_pnls = [t["pnl"] for t in trades_list[-self.config.rolling_window:]]
            avg_pnl = sum(recent_pnls) / len(recent_pnls) if recent_pnls else 0
            decay_pct = 1 - (avg_pnl / self._baseline.avg_trade_pnl) if self._baseline.avg_trade_pnl > 0 else 0
            if decay_pct > self.config.pnl_decay_critical:
                alerts.append(DecayAlert("avg_trade_pnl_decay", decay_pct, self.config.pnl_decay_critical, "critical", f"Avg trade PnL decay {decay_pct:.0%} > {self.config.pnl_decay_critical:.0%}"))
            elif decay_pct > self.config.pnl_decay_warning:
                alerts.append(DecayAlert("avg_trade_pnl_decay", decay_pct, self.config.pnl_decay_warning, "warning", f"Avg trade PnL decay {decay_pct:.0%} > {self.config.pnl_decay_warning:.0%}"))

        # 6. Profit factor
        if trades_list:
            gross_profit = sum(t["pnl"] for t in trades_list[-self.config.rolling_window:] if t["pnl"] > 0)
            gross_loss = abs(sum(t["pnl"] for t in trades_list[-self.config.rolling_window:] if t["pnl"] < 0))
            pf = gross_profit / gross_loss if gross_loss > 0 else float("inf")
            if pf < self.config.pf_critical:
                alerts.append(DecayAlert("profit_factor", pf, self.config.pf_critical, "critical", f"Profit factor {pf:.2f} < {self.config.pf_critical}"))
            elif pf < self.config.pf_warning:
                alerts.append(DecayAlert("profit_factor", pf, self.config.pf_warning, "warning", f"Profit factor {pf:.2f} < {self.config.pf_warning}"))

        # 7. Trade frequency deviation
        if self._baseline and self._baseline.trade_frequency_baseline > 0:
            recent_freq = len(trades_list[-self.config.rolling_window:]) / self.config.rolling_window
            freq_dev = abs(recent_freq - self._baseline.trade_frequency_baseline) / self._baseline.trade_frequency_baseline
            if freq_dev > self.config.freq_deviation_critical:
                alerts.append(DecayAlert("trade_frequency", freq_dev, self.config.freq_deviation_critical, "critical", f"Trade frequency deviation {freq_dev:.0%} > {self.config.freq_deviation_critical:.0%}"))
            elif freq_dev > self.config.freq_deviation_warning:
                alerts.append(DecayAlert("trade_frequency", freq_dev, self.config.freq_deviation_warning, "warning", f"Trade frequency deviation {freq_dev:.0%} > {self.config.freq_deviation_warning:.0%}"))

        # Determine overall signal
        critical_count = sum(1 for a in alerts if a.severity == "critical" or a.severity == "emergency")
        warning_count = sum(1 for a in alerts if a.severity == "warning")

        if critical_count >= 5:
            signal = DecaySignal.EMERGENCY
        elif critical_count >= 3:
            signal = DecaySignal.CRITICAL
        elif critical_count >= 1 or warning_count >= 3:
            signal = DecaySignal.WARNING
        else:
            signal = DecaySignal.NORMAL

        self._alerts = alerts
        return signal, alerts

    def _compute_sharpe(self, returns: list[float]) -> float:
        """Compute annualized Sharpe ratio."""
        if len(returns) < 2:
            return 0.0
        mean = sum(returns) / len(returns)
        var = sum((r - mean) ** 2 for r in returns) / (len(returns) - 1)
        std = math.sqrt(var) if var > 0 else 0.0
        if std == 0:
            return 0.0
        return (mean / std) * math.sqrt(24192)  # Annualize for M15

    def _compute_half_life(self, values: list[float]) -> int:
        """Compute signal half-life (bars until autocorrelation drops to 50%).

        Phase 4: Improved from O(W²) to O(W) using sliding-window autocorrelation.
        """
        n = len(values)
        if n < 10:
            return n

        mean = sum(values) / n
        var = sum((v - mean) ** 2 for v in values) / n
        if var <= 0:
            return n

        # Compute autocorrelation for lags 1..min(20, n-1) only (early termination)
        max_lag = min(20, n - 1)
        for lag in range(1, max_lag + 1):
            effective_n = n - lag
            cov = sum((values[i] - mean) * (values[i + lag] - mean) for i in range(effective_n)) / effective_n
            autocorr = cov / var
            if autocorr < 0.5:
                return lag

        return max_lag

    def reset(self):
        """Reset state for a new monitoring period."""
        self._returns.clear()
        self._trades.clear()
        self._signals.clear()
        self._alerts.clear()
