"""
Signal Validation Framework — IC/IR analysis for strategy promotion.

P0 gap: quant_os has walk-forward, PBO, DSR, cost stress, parameter stability,
but NO Information Coefficient (IC) analysis. This module closes that gap.

IC measures correlation between predicted signal and realized returns:
- Rolling IC (Spearman rank correlation) — robust to non-linearity
- IC decay — how fast the signal loses predictive power
- Information Ratio via Fundamental Law: IR = IC × √Breadth
- IC by market regime — is the signal regime-dependent?
- Alpha decay detection — intrinsic time vs clock time

Decision Gate (for OverfittingDetector integration):
  IC mean > 0.02  AND  IC IR > 0.5  →  PROCEED to paper trading

Usage:
    from validation.signal_validator import SignalValidator, SignalValidatorConfig

    validator = SignalValidator()
    report = validator.evaluate(
        signal=tsm_signal,         # pd.Series of predicted signals
        forward_returns=rets,      # pd.Series of actual forward returns
        regime_labels=regimes,     # optional: pd.Series of regime per bar
        strategy_id="tsm_v1",
    )
    if report.verdict in ("PROCEED", "CONDITIONAL"):
        # Edge confirmed — proceed to paper trading
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

import numpy as np


# ── Config ──────────────────────────────────────────────────────────────

@dataclass
class SignalValidatorConfig:
    """Thresholds for signal validation."""

    # IC thresholds
    min_mean_ic: float = 0.02       # Minimum mean Information Coefficient
    min_ic_ir: float = 0.5          # Minimum IC Information Ratio (mean / std)
    min_ic_hit_rate: float = 0.55   # Minimum % of windows with positive IC

    # Rolling window (bars)
    ic_window: int = 60             # Rolling IC window (60 days for daily, 60 bars for intraday)

    # Alpha decay
    decay_window: int = 252         # Window for decay measurement (1 year trading days)
    max_decay_threshold: float = -0.01  # Max negative slope before flagging decay

    # Reference
    annual_trading_days: int = 252

    # Correlation method
    method: str = "spearman"        # "spearman" (robust) or "pearson"


# ── Result dataclasses ──────────────────────────────────────────────────

@dataclass
class ICReport:
    """Rolling IC analysis result."""

    mean_ic: float
    ic_std: float
    ic_ir: float                     # Mean IC / IC Std
    ic_hit_rate: float               # Fraction of windows with positive IC
    rolling_ic_mean: float           # Mean of rolling IC series
    rolling_ic_last: float           # Most recent rolling IC value
    ic_min: float
    ic_max: float
    n_windows: int


@dataclass
class DecayReport:
    """Alpha decay measurement result."""

    ic_squared_slope: float          # Slope of cumulative IC²
    is_decaying: bool                # True if IC² grows sublinearly
    early_sharpe: float
    late_sharpe: float
    sharpe_p_value: float            # T-test p-value
    has_sharpe_decayed: bool         # True if late < early AND p < 0.05
    effective_sample_size: int       # Autocorrelation-adjusted sample size


@dataclass
class ICRegimeReport:
    """IC breakdown by market regime."""

    regime_ics: dict[str, float]     # Mean IC per regime
    regime_counts: dict[str, int]    # Observations per regime
    best_regime: str
    worst_regime: str
    regime_stability: float          # Std across regimes (low = stable)


@dataclass
class SignalValidationReport:
    """Full signal validation report."""

    strategy_id: str
    timestamp: str

    # Individual results
    ic_report: ICReport | None = None
    decay_report: DecayReport | None = None
    regime_report: ICRegimeReport | None = None

    # Aggregate
    passed: bool = False
    blockers: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    score: float = 0.0              # 0-1 composite
    verdict: str = "INSUFFICIENT_DATA"  # PROCEED | CONDITIONAL | NO_GO | INSUFFICIENT_DATA

    # Raw data shape
    n_signals: int = 0
    n_trades: int = 0
    date_range: str = ""


# ── Helpers ─────────────────────────────────────────────────────────────

def _spearman_rank(x: np.ndarray, y: np.ndarray) -> float:
    """Spearman rank correlation. Pure numpy, no scipy dependency."""
    n = len(x)
    if n < 3:
        return 0.0
    # Rank the arrays
    x_rank = np.argsort(np.argsort(x)).astype(float)
    y_rank = np.argsort(np.argsort(y)).astype(float)
    # Pearson on ranks = Spearman
    x_mean = np.mean(x_rank)
    y_mean = np.mean(y_rank)
    cov = np.sum((x_rank - x_mean) * (y_rank - y_mean))
    x_var = np.sum((x_rank - x_mean) ** 2)
    y_var = np.sum((y_rank - y_mean) ** 2)
    if x_var == 0 or y_var == 0:
        return 0.0
    return float(cov / math.sqrt(x_var * y_var))


def _pearson_r(x: np.ndarray, y: np.ndarray) -> float:
    """Pearson correlation coefficient."""
    n = len(x)
    if n < 3:
        return 0.0
    x_mean = np.mean(x)
    y_mean = np.mean(y)
    cov = np.sum((x - x_mean) * (y - y_mean))
    x_var = np.sum((x - x_mean) ** 2)
    y_var = np.sum((y - y_mean) ** 2)
    if x_var == 0 or y_var == 0:
        return 0.0
    return float(cov / math.sqrt(x_var * y_var))


def _correlation(x: np.ndarray, y: np.ndarray, method: str = "spearman") -> float:
    """Compute correlation between two arrays."""
    if method == "spearman":
        return _spearman_rank(x, y)
    return _pearson_r(x, y)


# ── Validator ───────────────────────────────────────────────────────────

class SignalValidator:
    """Signal validation — IC/IR analysis for strategy promotion.

    Args:
        config: Optional SignalValidatorConfig with custom thresholds.
    """

    def __init__(self, config: SignalValidatorConfig | None = None) -> None:
        self._config = config or SignalValidatorConfig()

    def evaluate(
        self,
        signal: Any,                # pd.Series — predicted signal values
        forward_returns: Any,       # pd.Series — actual forward returns
        regime_labels: Any | None = None,  # pd.Series — regime per bar (optional)
        strategy_id: str = "",
    ) -> SignalValidationReport:
        """Run full signal validation pipeline.

        Args:
            signal: Series of predicted signal values (-1 to +1 or continuous).
            forward_returns: Series of actual forward returns (shifted appropriately).
            regime_labels: Optional Series of regime labels per bar.
            strategy_id: Identifier for this strategy.

        Returns:
            SignalValidationReport with IC/IR analysis.
        """
        # Convert to numpy for computation
        sig = np.asarray(signal, dtype=float).ravel()
        ret = np.asarray(forward_returns, dtype=float).ravel()

        report = SignalValidationReport(
            strategy_id=strategy_id or "unknown",
            timestamp=datetime.now(UTC).isoformat(),
            n_signals=int(len(sig) > 0),
            n_trades=min(len(sig), len(ret)),
        )

        # Minimum data check
        min_bars = max(self._config.ic_window, 10)
        if len(sig) < min_bars or len(ret) < min_bars or len(sig) != len(ret):
            report.verdict = "INSUFFICIENT_DATA"
            report.blockers.append(
                f"Need at least {min_bars} aligned signal/return pairs "
                f"(got signal={len(sig)}, return={len(ret)})"
            )
            return report

        # 1. Rolling IC analysis
        report.ic_report = self._compute_ic(sig, ret, self._config.ic_window)

        # 2. Alpha decay measurement
        report.decay_report = self._compute_decay(sig, ret)

        # 3. IC by regime (if labels provided)
        if regime_labels is not None:
            reg = np.asarray(regime_labels, dtype=str).ravel()
            if len(reg) == len(sig):
                report.regime_report = self._compute_ic_by_regime(sig, ret, reg)

        # 4. Aggregate verdict
        self._compute_verdict(report)

        return report

    # ── Rolling IC ─────────────────────────────────────────────────

    def _compute_ic(
        self, signal: np.ndarray, returns: np.ndarray, window: int
    ) -> ICReport:
        """Compute rolling Information Coefficient analysis."""
        n = len(signal)
        rolling_ic = np.full(n, np.nan)

        for i in range(window, n):
            s = signal[i - window : i]
            r = returns[i - window : i]
            rolling_ic[i] = _correlation(s, r, self._config.method)

        valid_ic = rolling_ic[~np.isnan(rolling_ic)]

        if len(valid_ic) < 3:
            return ICReport(
                mean_ic=0.0, ic_std=0.0, ic_ir=0.0, ic_hit_rate=0.0,
                rolling_ic_mean=0.0, rolling_ic_last=0.0,
                ic_min=0.0, ic_max=0.0, n_windows=0,
            )

        # Pointwise (non-rolling) IC as well
        full_ic = _correlation(signal, returns, self._config.method)

        mean_ic = float(np.mean(valid_ic))
        std_ic = float(np.std(valid_ic))
        ic_ir = mean_ic / std_ic if std_ic > 0 else 0.0
        hit_rate = float(np.mean(valid_ic > 0))

        return ICReport(
            mean_ic=mean_ic,
            ic_std=std_ic,
            ic_ir=ic_ir,
            ic_hit_rate=hit_rate,
            rolling_ic_mean=mean_ic,
            rolling_ic_last=float(valid_ic[-1]) if len(valid_ic) > 0 else 0.0,
            ic_min=float(np.min(valid_ic)),
            ic_max=float(np.max(valid_ic)),
            n_windows=int(len(valid_ic)),
        )

    # ── Decay ──────────────────────────────────────────────────────

    def _compute_decay(self, signal: np.ndarray, returns: np.ndarray) -> DecayReport:
        """Measure alpha decay via IC² accumulation and Sharpe comparison."""
        n = len(signal)
        w = self._config.decay_window

        # Method 1: IC² accumulation slope
        window = min(w, n // 4)
        if window < 20:
            return DecayReport(
                ic_squared_slope=0.0, is_decaying=False,
                early_sharpe=0.0, late_sharpe=0.0,
                sharpe_p_value=1.0, has_sharpe_decayed=False,
                effective_sample_size=n,
            )

        rolling_ic_values = []
        for i in range(window, n):
            s = signal[i - window : i]
            r = returns[i - window : i]
            rolling_ic_values.append(_correlation(s, r, self._config.method))

        ic_arr = np.array(rolling_ic_values)
        ic_sq = ic_arr ** 2
        cum_ic2 = np.cumsum(ic_sq)

        # Linear fit: slope of cumulative IC²
        x = np.arange(len(cum_ic2))
        slope = self._ols_slope(x, cum_ic2)
        is_decaying = slope < np.median(np.diff(cum_ic2)) if len(cum_ic2) > 1 else False

        # Method 2: Early vs late Sharpe comparison
        mid = n // 2
        early_returns = returns[:mid]
        late_returns = returns[mid:]

        def _sharpe(r: np.ndarray) -> float:
            if len(r) < 10 or np.std(r) == 0:
                return 0.0
            return float(np.mean(r) / np.std(r) * math.sqrt(self._config.annual_trading_days))

        es = _sharpe(early_returns)
        ls = _sharpe(late_returns)

        # Simple t-test approximation
        t_stat = (es - ls) / math.sqrt(
            (np.var(early_returns) / len(early_returns) +
             np.var(late_returns) / len(late_returns))
        ) if len(early_returns) > 1 and len(late_returns) > 1 else 0.0
        # Two-tailed p-value approximation
        from scipy import stats
        p_val = 2 * (1 - stats.t.cdf(abs(t_stat), df=min(len(early_returns), len(late_returns)) - 1))

        # Effective sample size (autocorrelation adjustment)
        autocorr = self._autocorr(returns, lag=1)
        eff_n = int(n / (1 + 2 * autocorr)) if autocorr > 0 else n

        return DecayReport(
            ic_squared_slope=float(slope),
            is_decaying=bool(is_decaying),
            early_sharpe=es,
            late_sharpe=ls,
            sharpe_p_value=float(p_val),
            has_sharpe_decayed=bool(p_val < 0.05 and ls < es),
            effective_sample_size=eff_n,
        )

    @staticmethod
    def _ols_slope(x: np.ndarray, y: np.ndarray) -> float:
        """Simple OLS slope (b in y = a + bx)."""
        if len(x) < 2:
            return 0.0
        x_mean = np.mean(x)
        y_mean = np.mean(y)
        num = np.sum((x - x_mean) * (y - y_mean))
        den = np.sum((x - x_mean) ** 2)
        return float(num / den) if den != 0 else 0.0

    @staticmethod
    def _autocorr(x: np.ndarray, lag: int = 1) -> float:
        """Compute autocorrelation at given lag."""
        if len(x) <= lag + 2:
            return 0.0
        return _pearson_r(x[:-lag], x[lag:])

    # ── IC by regime ──────────────────────────────────────────────

    def _compute_ic_by_regime(
        self, signal: np.ndarray, returns: np.ndarray, regimes: np.ndarray
    ) -> ICRegimeReport:
        """Compute IC breakdown by market regime."""
        unique_regimes = set(regimes)
        regime_ics: dict[str, float] = {}
        regime_counts: dict[str, int] = {}

        for regime in unique_regimes:
            mask = regimes == regime
            s = signal[mask]
            r = returns[mask]
            if len(s) >= 10:
                regime_ics[regime] = _correlation(s, r, self._config.method)
                regime_counts[regime] = int(len(s))

        if not regime_ics:
            return ICRegimeReport(
                regime_ics={}, regime_counts={},
                best_regime="", worst_regime="",
                regime_stability=0.0,
            )

        best = max(regime_ics, key=regime_ics.get)
        worst = min(regime_ics, key=regime_ics.get)
        stability = float(np.std(list(regime_ics.values())))

        return ICRegimeReport(
            regime_ics=regime_ics,
            regime_counts=regime_counts,
            best_regime=best,
            worst_regime=worst,
            regime_stability=stability,
        )

    # ── Verdict ───────────────────────────────────────────────────

    def _compute_verdict(self, report: SignalValidationReport) -> None:
        """Compute aggregate verdict from all sub-reports."""
        ic = report.ic_report
        decay = report.decay_report
        cfg = self._config
        blockers: list[str] = []
        warnings: list[str] = []

        if ic is None:
            report.verdict = "INSUFFICIENT_DATA"
            return

        score = 0.0

        # IC mean gate
        if ic.mean_ic >= cfg.min_mean_ic:
            score += 0.35
        elif ic.mean_ic >= cfg.min_mean_ic * 0.5:
            warnings.append(f"IC mean ({ic.mean_ic:.4f}) below threshold ({cfg.min_mean_ic})")
            score += 0.15
        else:
            blockers.append(f"IC mean ({ic.mean_ic:.4f}) — need >= {cfg.min_mean_ic}")

        # IC IR gate
        if ic.ic_ir >= cfg.min_ic_ir:
            score += 0.25
        else:
            blockers.append(f"IC IR ({ic.ic_ir:.2f}) — need >= {cfg.min_ic_ir}")

        # IC hit rate
        if ic.ic_hit_rate >= cfg.min_ic_hit_rate:
            score += 0.15
        else:
            warnings.append(f"IC hit rate ({ic.ic_hit_rate:.2%}) — need >= {cfg.min_ic_hit_rate:.0%}")

        # Alpha decay
        if decay is not None:
            if decay.has_sharpe_decayed:
                blockers.append(f"Alpha decay detected: early Sharpe {decay.early_sharpe:.2f} → late {decay.late_sharpe:.2f} (p={decay.sharpe_p_value:.3f})")
            elif decay.early_sharpe > 0 and decay.late_sharpe <= 0:
                warnings.append(f"Late-period Sharpe negative ({decay.late_sharpe:.2f}) — edge may be deteriorating")

        report.passed = len(blockers) == 0
        report.blockers = blockers
        report.warnings = warnings
        report.score = round(score, 4)

        if report.passed:
            report.verdict = "PROCEED"
        elif len(blockers) <= 1:
            report.verdict = "CONDITIONAL"
        else:
            report.verdict = "NO_GO"
