"""Dynamic spread/slippage model for backtest — replaces fixed spread_pips."""
from decimal import Decimal
from dataclasses import dataclass


@dataclass
class SpreadConfig:
    """Session-aware spread configuration for XAUUSD on Pepperstone Razor."""
    asian_spread: float = 3.0    # pips — wider during low liquidity
    london_spread: float = 1.5   # pips — tight during London
    ny_spread: float = 1.5       # pips — tight during NY
    overlap_spread: float = 1.2  # pips — tightest during London/NY overlap
    closed_spread: float = 5.0   # pips — very wide during closed hours

    # Slippage multipliers by volatility regime
    low_vol_slippage_mult: float = 0.5
    normal_vol_slippage_mult: float = 1.0
    high_vol_slippage_mult: float = 2.0

    def get_spread(self, utc_hour: int) -> Decimal:
        """Get spread in pips based on UTC hour."""
        if 0 <= utc_hour < 7:    # Asian session
            return Decimal(str(self.asian_spread))
        elif 7 <= utc_hour < 13:  # London session
            return Decimal(str(self.london_spread))
        elif 13 <= utc_hour < 17:  # London/NY overlap
            return Decimal(str(self.overlap_spread))
        elif 17 <= utc_hour < 21:  # NY session
            return Decimal(str(self.ny_spread))
        else:  # Closed (21-00)
            return Decimal(str(self.closed_spread))

    def get_slippage(self, utc_hour: int, atr: float = 1.0) -> Decimal:
        """Get slippage in pips based on session and volatility."""
        base_slip = Decimal("0.3")  # base slippage for XAUUSD
        if atr < 0.5:
            mult = self.low_vol_slippage_mult
        elif atr > 2.0:
            mult = self.high_vol_slippage_mult
        else:
            mult = self.normal_vol_slippage_mult
        return base_slip * Decimal(str(mult))
