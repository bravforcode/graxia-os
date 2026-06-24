"""Base strategy class for Quant OS"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import Decimal
from typing import Optional, Dict, Any, List
from uuid import uuid4

from ..core.enums import SignalType, RegimeType
from ..risk.contract_spec import ContractSpec, ContractSpecError


@dataclass
class Signal:
    """Trading signal from a strategy"""
    id: str
    strategy_id: str
    symbol: str
    signal_type: SignalType
    timestamp: datetime
    
    # Signal strength
    confidence: float = 0.0  # 0.0 to 1.0
    strength: str = "medium"  # weak, medium, strong
    
    # Price levels
    entry_price: Optional[Decimal] = None
    stop_loss: Optional[Decimal] = None
    take_profit: Optional[Decimal] = None
    
    # Context
    regime: Optional[RegimeType] = None
    timeframe: str = "M15"
    
    # Indicators
    indicator_values: Dict[str, Any] = field(default_factory=dict)
    
    # Metadata
    raw_payload: Optional[Dict] = None
    notes: str = ""
    
    @classmethod
    def create(
        cls,
        strategy_id: str,
        symbol: str,
        signal_type: SignalType,
        confidence: float = 0.0,
        **kwargs
    ) -> "Signal":
        """Factory method to create a signal"""
        return cls(
            id=str(uuid4()),
            strategy_id=strategy_id,
            symbol=symbol,
            signal_type=signal_type,
            timestamp=datetime.now(timezone.utc),
            confidence=confidence,
            **kwargs
        )
    
    @property
    def is_buy(self) -> bool:
        return self.signal_type == SignalType.BUY
    
    @property
    def is_sell(self) -> bool:
        return self.signal_type == SignalType.SELL
    
    @property
    def risk_reward_ratio(self) -> Optional[float]:
        """Calculate risk/reward ratio if SL and TP are set"""
        if self.stop_loss is None or self.take_profit is None or self.entry_price is None:
            return None
        
        risk = abs(float(self.entry_price) - float(self.stop_loss))
        reward = abs(float(self.take_profit) - float(self.entry_price))
        
        if risk == 0:
            return None
        
        return reward / risk


@dataclass
class StrategyConfig:
    """Configuration for a strategy"""
    name: str
    version: str = "1.0.0"
    
    # Symbols and timeframes
    symbols: List[str] = field(default_factory=list)
    timeframes: List[str] = field(default_factory=lambda: ["M15"])
    
    # Risk parameters
    risk_per_trade_pct: float = 1.0
    max_trades_per_day: int = 5
    
    # Entry/exit rules
    min_confidence: float = 0.60
    min_risk_reward: float = 1.5
    
    # Filters
    require_trend_confirm: bool = True
    require_volume_spike: bool = False
    regime_filter: Optional[List[RegimeType]] = None


class Strategy(ABC):
    """
    Abstract base class for trading strategies.
    
    All strategies must implement:
    - generate_signal(): Produce trading signals from market data
    - required_features(): List required features/indicators
    - is_valid_for_regime(): Check if strategy is valid for current regime
    """
    
    def __init__(self, config: Optional[StrategyConfig] = None):
        self.config = config or StrategyConfig(name=self.__class__.__name__)
        self.id = f"{self.__class__.__name__}_{self.config.version}"
        
        # Performance tracking
        self.signals_generated: int = 0
        self.trades_taken: int = 0
        self.win_count: int = 0
        self.loss_count: int = 0
    
    @abstractmethod
    def generate_signal(
        self,
        symbol: str,
        ohlcv_data: Dict[str, List],  # OHLCV data
        indicators: Optional[Dict[str, Any]] = None,
        regime: Optional[RegimeType] = None,
        **kwargs,
    ) -> Optional[Signal]:
        """
        Generate trading signal from market data.
        
        Args:
            symbol: Trading symbol (e.g., "EURUSD")
            ohlcv_data: Dictionary with 'open', 'high', 'low', 'close', 'volume' arrays
            indicators: Pre-calculated indicators (optional)
            regime: Current market regime (optional)
        
        Returns:
            Signal if conditions met, None otherwise
        """
        pass
    
    @abstractmethod
    def required_features(self) -> List[str]:
        """
        Return list of required features/indicators.
        
        Returns:
            List of feature names (e.g., ["ema_9", "ema_20", "rsi_14"])
        """
        pass
    
    def is_valid_for_regime(self, regime: RegimeType) -> bool:
        """
        Check if strategy is valid for given market regime.
        Override for regime-specific strategies.
        """
        if self.config.regime_filter is None:
            return True
        return regime in self.config.regime_filter
    
    def calculate_position_size(
        self,
        account_balance: Decimal,
        entry_price: Decimal,
        stop_loss: Decimal,
        risk_pct: Optional[float] = None,
        contract_spec: ContractSpec = None,
    ) -> Decimal:
        """
        Calculate position size based on risk parameters.
        
        Args:
            account_balance: Current account balance
            entry_price: Planned entry price
            stop_loss: Stop loss price
            risk_pct: Risk percentage (default from config)
            contract_spec: ContractSpec for the symbol (mandatory)
        
        Returns:
            Position size in lots
        """
        if contract_spec is None:
            raise ContractSpecError("ContractSpec required for position sizing", "unknown")
        
        risk_amount = account_balance * Decimal(str(risk_pct or self.config.risk_per_trade_pct)) / 100
        
        price_risk = abs(entry_price - stop_loss)
        if price_risk == 0:
            return Decimal("0")
        
        units = risk_amount / price_risk
        lots = units / Decimal(str(contract_spec.contract_size))
        
        return lots.quantize(Decimal("0.01"))
    
    def record_outcome(self, pnl: float) -> None:
        """Record trade outcome for performance tracking"""
        self.trades_taken += 1
        if pnl > 0:
            self.win_count += 1
        elif pnl < 0:
            self.loss_count += 1
    
    @property
    def win_rate(self) -> float:
        """Calculate win rate"""
        if self.trades_taken == 0:
            return 0.0
        return self.win_count / self.trades_taken
    
    def get_stats(self) -> Dict[str, Any]:
        """Get strategy statistics"""
        return {
            "id": self.id,
            "name": self.config.name,
            "version": self.config.version,
            "signals_generated": self.signals_generated,
            "trades_taken": self.trades_taken,
            "win_count": self.win_count,
            "loss_count": self.loss_count,
            "win_rate": self.win_rate,
        }
