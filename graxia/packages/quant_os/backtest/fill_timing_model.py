"""Fill timing model — models execution latency between signal and fill."""
from dataclasses import dataclass
from decimal import Decimal


@dataclass
class FillTimingConfig:
    """Execution latency model for backtest-vs-live comparison."""

    # Latency in milliseconds (observed from Pepperstone Razor)
    base_latency_ms: float = 50.0       # minimum network + broker processing
    max_latency_ms: float = 300.0       # worst case during high volatility
    avg_latency_ms: float = 120.0       # typical during normal conditions

    # Slippage per ms of latency (in price units per pip)
    slippage_per_ms: float = 0.001      # 0.001 pips per ms of latency

    # Volatility multiplier (ATR-based)
    low_vol_latency_mult: float = 0.8   # faster fills in low vol
    high_vol_latency_mult: float = 2.0  # slower fills in high vol

    def estimate_latency_ms(self, atr: float = 1.0) -> float:
        """Estimate fill latency in ms based on current volatility."""
        if atr < 0.5:
            mult = self.low_vol_latency_mult
        elif atr > 2.0:
            mult = self.high_vol_latency_mult
        else:
            mult = 1.0
        return self.avg_latency_ms * mult

    def estimate_slippage_pips(self, latency_ms: float, volatility_regime: str = "normal") -> Decimal:
        """Estimate additional slippage from latency."""
        base_slip = Decimal("0.3")  # base slippage for XAUUSD
        latency_slip = Decimal(str(latency_ms * self.slippage_per_ms))
        return base_slip + latency_slip
