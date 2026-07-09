"""Pipeline configuration for parallel validation."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class PipelineConfig:
    """Configuration for the full validation pipeline."""

    # Assets
    symbols: list[str] = field(default_factory=lambda: ["XAUUSD", "EURUSD"])
    timeframe: str = "H1"  # H1 or D1
    data_dir: Path = Path("data")
    reports_dir: Path = Path("reports/validation")

    # Walk-Forward
    wfa_n_windows: int = 8
    wfa_is_ratio: float = 0.7
    wfa_mode: str = "rolling"  # "rolling" or "anchored"
    wfa_purge_bars: int = 0

    # Monte Carlo
    mc_n_sims: int = 10_000
    mc_n_trades_forward: int = 540
    mc_starting_balance: float = 5000.0
    mc_kill_switch_balance: float = 4500.0

    # DSR
    dsr_n_trials: int = 50  # Number of strategy configs tested

    # PBO
    pbo_n_combinations: int | None = None  # None = all, cap 512

    # Bootstrap
    bootstrap_n_resamples: int = 5_000
    bootstrap_block_length: int = 20
    bootstrap_confidence: float = 0.95

    # Synthetic
    synthetic_n_paths: int = 5_000
    synthetic_block_size: int = 20

    # Stress
    stress_scenarios: list[str] = field(
        default_factory=lambda: ["market_crash", "flash_crash", "correlation_breakdown", "liquidity_crisis"]
    )

    # Gate thresholds
    wfa_min_oos_positive: float = 0.70  # 70% of OOS windows positive
    wfa_min_wfe: float = 0.50
    wfa_max_degradation: float = 0.30
    mc_max_ruin_prob: float = 0.05
    mc_max_dd_p95: float = 0.25
    dsr_min_value: float = 0.0
    pbo_max_value: float = 0.50
    stress_min_positive: float = 0.80
    bootstrap_sharpe_ci_lower_min: float = 0.0

    # Live testing
    live_enabled: bool = True
    live_max_loss_usd: float = 10.0
    live_lot_size: float = 0.01
    live_duration_days: int = 7

    # Parallel execution
    max_workers: int = 4

    def data_path(self, symbol: str) -> Path:
        """Get path to symbol data file."""
        return self.data_dir / f"{symbol}_{self.timeframe}.csv"

    def validate(self) -> list[str]:
        """Return list of validation errors (empty = valid)."""
        errors = []
        for sym in self.symbols:
            if not self.data_path(sym).exists():
                errors.append(f"Missing data: {self.data_path(sym)}")
        if self.wfa_n_windows < 3:
            errors.append("wfa_n_windows must be >= 3")
        if self.mc_n_sims < 1000:
            errors.append("mc_n_sims must be >= 1000")
        return errors


def default_config() -> PipelineConfig:
    """Return default config for XAUUSD + EURUSD H1."""
    return PipelineConfig(
        symbols=["XAUUSD", "EURUSD"],
        timeframe="H1",
    )
