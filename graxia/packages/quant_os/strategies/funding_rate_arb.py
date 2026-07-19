"""
Funding Rate Arbitrage — Exploit perpetual funding rate imbalances.

Expected improvement: +10-15% annual (low risk).

ponytail: Simple funding rate threshold. Upgrade path: multi-exchange arb.
"""

from __future__ import annotations

from decimal import Decimal

from ..core.enums import SignalType, RegimeType
from .base import Signal, Strategy, StrategyConfig


class FundingRateArbitrage(Strategy):
    """Strategy based on perpetual funding rate imbalances.

    When funding rate is high positive (shorts pay longs):
    - Short perpetual
    - Long spot
    - Collect funding payments

    When funding rate is high negative (longs pay shorts):
    - Long perpetual
    - Short spot (if possible)
    - Collect funding payments

    Example:
        strategy = FundingRateArbitrage()
        signal = strategy.generate_signal(
            'BTCUSD', ohlcv_data, funding_rate=0.0003
        )
    """

    def __init__(self, config: StrategyConfig | None = None):
        super().__init__(
            config
            or StrategyConfig(
                name="FundingRateArb",
                version="1.0.0",
                symbols=["BTCUSD", "ETHUSD"],
                min_confidence=0.65,
            )
        )
        self.min_annual_rate = 0.10  # 10% annual minimum
        self.max_annual_rate = 0.50  # 50% annual max (too good to be true)

    def generate_signal(
        self,
        symbol: str,
        ohlcv_data: dict[str, list],
        indicators: dict | None = None,
        regime: RegimeType | None = None,
        **kwargs,
    ) -> Signal | None:
        """Generate signal based on funding rate.

        Args:
            symbol: Trading symbol
            ohlcv_data: OHLCV data dict
            indicators: Pre-computed indicators
            regime: Current market regime
            **kwargs: Must include 'funding_rate' (float)

        Returns:
            Signal if funding rate is attractive, None otherwise
        """
        funding_rate = kwargs.get("funding_rate")
        if funding_rate is None:
            return None

        annual_rate = funding_rate * 3 * 365  # 3x daily funding

        # Positive funding = shorts pay longs = short perp, long spot
        if annual_rate > self.min_annual_rate:
            confidence = min(annual_rate / 0.20, 1.0)

            close_list = ohlcv_data.get("close", [])
            if not close_list:
                return None
            current_price = Decimal(str(close_list[-1]))

            return Signal.create(
                strategy_id=self.config.name,
                symbol=symbol,
                signal_type=SignalType.SELL,  # Short perp
                confidence=confidence,
                entry_price=current_price,
                notes=f"Funding rate: {annual_rate:.1%} annual - short perp, long spot",
                indicator_values={
                    "funding_rate": funding_rate,
                    "annual_rate": annual_rate,
                    "action": "short_perp_long_spot",
                },
            )

        return None

    def required_features(self) -> list[str]:
        return ["funding_rate"]
