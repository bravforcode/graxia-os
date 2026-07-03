"""Risk policy in basis points. Replaces all _pct risk fields in production code."""

from dataclasses import dataclass
from decimal import Decimal


@dataclass(frozen=True)
class RiskPolicy:
    """Immutable risk policy. All loss limits in basis points (1 bps = 0.01%)."""

    risk_per_trade_bps: int = 100  # 1.00% — matches QuantConfig legacy default
    max_daily_loss_bps: int = 200  # 2.00% — matches QuantConfig legacy default
    max_weekly_loss_bps: int = 500  # 5.00% — matches QuantConfig legacy default
    max_total_drawdown_bps: int = 1000  # 10.00% — matches QuantConfig legacy default
    max_open_positions: int = 5
    max_orders_per_day: int = 3
    max_symbol_exposure_bps: int = 100  # 1.00%
    max_gross_exposure_bps: int = 100  # 1.00%
    reject_if_margin_level_below_pct: int = 500
    reject_if_data_stale_seconds: int = 5
    reject_if_spread_multiplier_above: float = 2.0
    reject_if_slippage_estimate_exceeds_r: float = 0.20
    require_stop_loss: bool = True
    require_contract_snapshot: bool = True
    require_order_check: bool = True
    fail_closed: bool = True
    strict_mtf: bool = True  # No static fallback allowed

    @property
    def risk_per_trade_fraction(self) -> Decimal:
        """Convert bps to fraction: 10 bps = 0.0010"""
        return Decimal(self.risk_per_trade_bps) / Decimal(10000)

    @property
    def max_daily_loss_fraction(self) -> Decimal:
        return Decimal(self.max_daily_loss_bps) / Decimal(10000)

    @property
    def max_weekly_loss_fraction(self) -> Decimal:
        return Decimal(self.max_weekly_loss_bps) / Decimal(10000)

    @property
    def max_total_drawdown_fraction(self) -> Decimal:
        return Decimal(self.max_total_drawdown_bps) / Decimal(10000)

    # --- Backward-compatible pct-based aliases (for callers that still use old names) ---

    @property
    def max_risk_per_trade_pct(self) -> Decimal:
        """Pct alias: risk_per_trade_bps / 100."""
        return Decimal(self.risk_per_trade_bps) / Decimal(100)

    @property
    def max_daily_loss_pct(self) -> Decimal:
        """Pct alias: max_daily_loss_bps / 100."""
        return Decimal(self.max_daily_loss_bps) / Decimal(100)

    @property
    def max_weekly_loss_pct(self) -> Decimal:
        """Pct alias: max_weekly_loss_bps / 100."""
        return Decimal(self.max_weekly_loss_bps) / Decimal(100)

    @property
    def max_drawdown_pct(self) -> Decimal:
        """Pct alias: max_total_drawdown_bps / 100."""
        return Decimal(self.max_total_drawdown_bps) / Decimal(100)

    @property
    def max_positions(self) -> int:
        """Alias for max_open_positions."""
        return self.max_open_positions

    @property
    def min_margin_level_pct(self) -> Decimal:
        """Alias for reject_if_margin_level_below_pct."""
        return Decimal(self.reject_if_margin_level_below_pct)


def validate_no_pct_in_production() -> list[str]:
    """
    Scans production code paths for risk_per_trade_pct usage.
    Returns list of violations (empty = clean).
    """
    import importlib

    violations = []
    production_modules = [
        "graxia.packages.quant_os.core.config",
        "graxia.packages.quant_os.backtest.engine",
        "graxia.packages.quant_os.risk.engine",
        "graxia.packages.quant_os.risk.position_sizer",
        "graxia.packages.quant_os.strategies.base",
    ]
    for mod_name in production_modules:
        try:
            mod = importlib.import_module(mod_name)
            source = getattr(mod, "__file__", "")
            if source:
                with open(source) as f:
                    for i, line in enumerate(f, 1):
                        if "risk_per_trade_pct" in line and not line.strip().startswith("#"):
                            violations.append(f"{mod_name}:{i}: {line.strip()}")
        except (ImportError, FileNotFoundError):
            pass
    return violations
