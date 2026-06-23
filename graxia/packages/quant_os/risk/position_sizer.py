"""
Position Sizing Algorithms for Quant OS

Implements multiple position sizing methods:
1. Fixed Fractional (1% risk per trade)
2. Kelly Criterion (optimal growth)
3. ATR-based volatility sizing
4. Anti-Martingale (reduce after losses)
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from decimal import Decimal, ROUND_DOWN
from typing import Optional

from ..core.config import get_config
from ..core.golden_rules import GOLDEN_RULES
from .contract_spec import ContractSpec, ContractSpecError


@dataclass
class PositionSizeResult:
    """Position sizing result"""
    lots: Decimal
    units: Decimal
    notional_value: Decimal
    risk_amount: Decimal
    risk_pct: float
    method: str
    notes: str = ""


class PositionSizer(ABC):
    """Abstract base class for position sizing"""
    
    def __init__(self, name: str):
        self.name = name
        self.config = get_config()
    
    @abstractmethod
    def calculate(
        self,
        account_balance: Decimal,
        entry_price: Decimal,
        stop_loss: Decimal,
        symbol: str = "",
        contract_spec: ContractSpec = None,
        **kwargs
    ) -> PositionSizeResult:
        """
        Calculate position size.
        
        Args:
            account_balance: Current account balance
            entry_price: Planned entry price
            stop_loss: Stop loss price
            symbol: Trading symbol
            contract_spec: ContractSpec for the symbol (mandatory, fail closed if None)
            **kwargs: Additional parameters specific to sizer
        
        Returns:
            PositionSizeResult with calculated size
        """
        pass
    
    def _require_contract_spec(
        self, contract_spec: ContractSpec = None, symbol: str = ""
    ) -> int:
        """Get contract_size from spec or fail closed."""
        if contract_spec is None:
            raise ContractSpecError("ContractSpec required for position sizing", symbol or "unknown")
        return contract_spec.contract_size
    
    def _apply_limits(
        self,
        lots: Decimal,
        units: Decimal,
        notional: Decimal,
        account_balance: Decimal
    ) -> tuple:
        """
        Apply position size limits.
        
        Returns:
            (limited_lots, limited_units, limited_notional)
        """
        # Get mode-specific limits
        limits = self.config.get_mode_risk_limits()
        max_position_size = limits.get("max_position_size", float('inf'))
        
        # Apply max position size limit
        if max_position_size != float('inf'):
            max_notional = Decimal(str(max_position_size))
            if notional > max_notional:
                ratio = max_notional / notional
                lots = (lots * ratio).quantize(Decimal("0.01"), rounding=ROUND_DOWN)
                units = (units * ratio).quantize(Decimal("1"), rounding=ROUND_DOWN)
                notional = max_notional
        
        # Max exposure limit
        max_exposure = account_balance * Decimal(str(self.config.max_portfolio_exposure_pct)) / 100
        if notional > max_exposure:
            ratio = max_exposure / notional
            lots = (lots * ratio).quantize(Decimal("0.01"), rounding=ROUND_DOWN)
            units = (units * ratio).quantize(Decimal("1"), rounding=ROUND_DOWN)
            notional = max_exposure
        
        return lots, units, notional


class FixedFractionalSizer(PositionSizer):
    """
    Fixed Fractional Position Sizing.
    
    Risk fixed percentage of account per trade.
    Default: 1% as per golden rules.
    """
    
    def __init__(self, risk_pct: Optional[float] = None):
        super().__init__("FixedFractional")
        self.risk_pct = risk_pct or GOLDEN_RULES.MAX_RISK_PER_TRADE_PCT
    
    def calculate(
        self,
        account_balance: Decimal,
        entry_price: Decimal,
        stop_loss: Decimal,
        symbol: str = "",
        contract_spec: ContractSpec = None,
        **kwargs
    ) -> PositionSizeResult:
        """Calculate position size based on fixed risk percentage"""
        contract_size = self._require_contract_spec(contract_spec, symbol)
        
        risk_amount = account_balance * Decimal(str(self.risk_pct)) / 100
        price_risk = abs(entry_price - stop_loss)
        
        if price_risk == 0:
            return PositionSizeResult(
                lots=Decimal("0"),
                units=Decimal("0"),
                notional_value=Decimal("0"),
                risk_amount=Decimal("0"),
                risk_pct=0.0,
                method=self.name,
                notes="Stop loss at entry price - cannot calculate size"
            )
        
        units = risk_amount / price_risk
        lots = units / Decimal(str(contract_size))
        lots = lots.quantize(Decimal("0.01"), rounding=ROUND_DOWN)
        units = lots * Decimal(str(contract_size))
        notional = units * entry_price
        
        lots, units, notional = self._apply_limits(lots, units, notional, account_balance)
        
        actual_risk = units * price_risk
        actual_risk_pct = float(actual_risk / account_balance * 100)
        
        return PositionSizeResult(
            lots=lots,
            units=units,
            notional_value=notional,
            risk_amount=actual_risk,
            risk_pct=actual_risk_pct,
            method=self.name,
            notes=f"Risk {actual_risk_pct:.2f}% of account"
        )


class KellySizer(PositionSizer):
    """
    Kelly Criterion Position Sizing.
    
    Optimal fraction for maximum growth based on:
    f = (bp - q) / b
    where:
    b = average win / average loss (payoff ratio)
    p = win probability
    q = 1 - p (loss probability)
    
    Uses half-Kelly for safety (conservative Kelly).
    """
    
    def __init__(self, win_rate: float = 0.55, avg_win: float = 1.5, avg_loss: float = 1.0):
        super().__init__("Kelly")
        self.win_rate = win_rate
        self.avg_win = avg_win
        self.avg_loss = avg_loss
        self.kelly_fraction = 0.5  # Half-Kelly for safety
    
    def calculate(
        self,
        account_balance: Decimal,
        entry_price: Decimal,
        stop_loss: Decimal,
        symbol: str = "",
        contract_spec: ContractSpec = None,
        **kwargs
    ) -> PositionSizeResult:
        """Calculate position size using Kelly Criterion"""
        contract_size = self._require_contract_spec(contract_spec, symbol)
        
        p = self.win_rate
        q = 1 - p
        b = self.avg_win / self.avg_loss
        
        kelly_pct = (b * p - q) / b
        adjusted_kelly = kelly_pct * self.kelly_fraction
        
        max_risk = GOLDEN_RULES.MAX_RISK_PER_TRADE_PCT / 100
        if adjusted_kelly > max_risk:
            adjusted_kelly = max_risk
            capped = True
        else:
            capped = False
        
        risk_pct = adjusted_kelly * 100
        risk_amount = account_balance * Decimal(str(risk_pct)) / 100
        price_risk = abs(entry_price - stop_loss)
        
        if price_risk == 0:
            return PositionSizeResult(
                lots=Decimal("0"),
                units=Decimal("0"),
                notional_value=Decimal("0"),
                risk_amount=Decimal("0"),
                risk_pct=0.0,
                method=self.name,
                notes="Stop loss at entry price"
            )
        
        units = risk_amount / price_risk
        lots = units / Decimal(str(contract_size))
        lots = lots.quantize(Decimal("0.01"), rounding=ROUND_DOWN)
        units = lots * Decimal(str(contract_size))
        notional = units * entry_price
        
        lots, units, notional = self._apply_limits(lots, units, notional, account_balance)
        
        actual_risk = units * price_risk
        actual_risk_pct = float(actual_risk / account_balance * 100)
        
        notes = f"Kelly: {kelly_pct*100:.2f}%, Using: {risk_pct:.2f}% (half-Kelly)"
        if capped:
            notes += " [capped by golden rule]"
        
        return PositionSizeResult(
            lots=lots,
            units=units,
            notional_value=notional,
            risk_amount=actual_risk,
            risk_pct=actual_risk_pct,
            method=self.name,
            notes=notes
        )
    
    def update_stats(self, win_rate: float, avg_win: float, avg_loss: float) -> None:
        """Update Kelly parameters from historical performance"""
        self.win_rate = win_rate
        self.avg_win = avg_win
        self.avg_loss = avg_loss


class ATRSizer(PositionSizer):
    """
    ATR-based Position Sizing.
    
    Adjusts position size based on market volatility (ATR).
    Higher volatility = smaller position.
    """
    
    def __init__(self, atr_multiple: float = 1.5, base_risk_pct: float = 1.0):
        super().__init__("ATR")
        self.atr_multiple = atr_multiple
        self.base_risk_pct = base_risk_pct
    
    def calculate(
        self,
        account_balance: Decimal,
        entry_price: Decimal,
        stop_loss: Decimal,
        symbol: str = "",
        contract_spec: ContractSpec = None,
        atr: Optional[Decimal] = None,
        **kwargs
    ) -> PositionSizeResult:
        """Calculate position size based on ATR volatility"""
        # NOTE: contract_spec required even for fallback path
        contract_size = self._require_contract_spec(contract_spec, symbol)
        
        if atr is None or atr == 0:
            fallback = FixedFractionalSizer(self.base_risk_pct)
            result = fallback.calculate(
                account_balance, entry_price, stop_loss, symbol,
                contract_spec=contract_spec,
            )
            result.method = f"{self.name} (fallback to FixedFractional)"
            return result
        
        atr_stop_distance = atr * Decimal(str(self.atr_multiple))
        risk_amount = account_balance * Decimal(str(self.base_risk_pct)) / 100
        
        units = risk_amount / atr_stop_distance
        lots = units / Decimal(str(contract_size))
        lots = lots.quantize(Decimal("0.01"), rounding=ROUND_DOWN)
        units = lots * Decimal(str(contract_size))
        notional = units * entry_price
        
        lots, units, notional = self._apply_limits(lots, units, notional, account_balance)
        
        actual_risk = units * atr_stop_distance
        actual_risk_pct = float(actual_risk / account_balance * 100)
        
        return PositionSizeResult(
            lots=lots,
            units=units,
            notional_value=notional,
            risk_amount=actual_risk,
            risk_pct=actual_risk_pct,
            method=self.name,
            notes=f"ATR: {float(atr):.5f}, Stop: {float(atr_stop_distance):.5f} ({self.atr_multiple}× ATR)"
        )


class AntiMartingaleSizer(PositionSizer):
    """
    Anti-Martingale Position Sizing.
    
    Increases position size after wins, decreases after losses.
    Opposite of dangerous Martingale strategy.
    """
    
    def __init__(
        self,
        base_risk_pct: float = 1.0,
        consecutive_losses: int = 0,
        consecutive_wins: int = 0,
    ):
        super().__init__("AntiMartingale")
        self.base_risk_pct = base_risk_pct
        self.consecutive_losses = consecutive_losses
        self.consecutive_wins = consecutive_wins
    
    def calculate(
        self,
        account_balance: Decimal,
        entry_price: Decimal,
        stop_loss: Decimal,
        symbol: str = "",
        contract_spec: ContractSpec = None,
        **kwargs
    ) -> PositionSizeResult:
        """Calculate position size with anti-martingale adjustment"""
        contract_size = self._require_contract_spec(contract_spec, symbol)
        
        adjustment = 1.0
        
        if self.consecutive_losses >= 3:
            adjustment = 0.25
        elif self.consecutive_losses >= 2:
            adjustment = 0.5
        
        if self.consecutive_wins >= 3:
            adjustment = min(adjustment * 1.5, 2.0)
        elif self.consecutive_wins >= 2:
            adjustment = min(adjustment * 1.25, 1.5)
        
        adjusted_risk = self.base_risk_pct * adjustment
        adjusted_risk = min(adjusted_risk, GOLDEN_RULES.MAX_RISK_PER_TRADE_PCT)
        
        risk_amount = account_balance * Decimal(str(adjusted_risk)) / 100
        price_risk = abs(entry_price - stop_loss)
        
        if price_risk == 0:
            return PositionSizeResult(
                lots=Decimal("0"),
                units=Decimal("0"),
                notional_value=Decimal("0"),
                risk_amount=Decimal("0"),
                risk_pct=0.0,
                method=self.name,
                notes="Stop loss at entry price"
            )
        
        units = risk_amount / price_risk
        lots = units / Decimal(str(contract_size))
        lots = lots.quantize(Decimal("0.01"), rounding=ROUND_DOWN)
        units = lots * Decimal(str(contract_size))
        notional = units * entry_price
        
        lots, units, notional = self._apply_limits(lots, units, notional, account_balance)
        
        actual_risk = units * price_risk
        actual_risk_pct = float(actual_risk / account_balance * 100)
        
        notes_parts = [f"Base: {self.base_risk_pct}%, Adj: {adjusted_risk:.2f}%"]
        if self.consecutive_losses > 0:
            notes_parts.append(f"({self.consecutive_losses} losses)")
        elif self.consecutive_wins > 0:
            notes_parts.append(f"({self.consecutive_wins} wins)")
        
        return PositionSizeResult(
            lots=lots,
            units=units,
            notional_value=notional,
            risk_amount=actual_risk,
            risk_pct=actual_risk_pct,
            method=self.name,
            notes=" ".join(notes_parts)
        )
    
    def record_outcome(self, pnl: float) -> None:
        """Record trade outcome for streak tracking"""
        if pnl > 0:
            self.consecutive_wins += 1
            self.consecutive_losses = 0
        elif pnl < 0:
            self.consecutive_losses += 1
            self.consecutive_wins = 0
        else:
            # Breakeven - reset both
            self.consecutive_wins = 0
            self.consecutive_losses = 0


def get_default_sizer() -> PositionSizer:
    """Get default position sizer based on configuration"""
    config = get_config()
    return FixedFractionalSizer(config.max_risk_per_trade_pct)
