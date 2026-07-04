"""
Gold Bot Configuration
"""

from dataclasses import dataclass, field
from typing import List, Optional
import os


@dataclass
class BotConfig:
    """Gold Bot configuration"""
    
    # === SYMBOL ===
    symbol: str = "XAUUSD"
    
    # === TIMEFRAMES ===
    primary_timeframe: str = "M15"
    timeframes: List[str] = field(default_factory=lambda: ["M1", "M5", "M15", "H1", "H4"])
    
    # === EXECUTION ===
    cycle_interval_seconds: int = 30
    
    # === SCORING ===
    min_score_to_trade: int = 350  # Minimum aggregate score to execute (conservative)
    min_active_strategies: int = 3  # Minimum strategies that must agree
    
    # === RISK MANAGEMENT ===
    initial_capital: float = 10000.0
    max_risk_per_trade_pct: float = 0.25  # Conservative: 0.25% per trade
    max_daily_loss_pct: float = 2.0       # Stop trading at 2% daily loss
    max_drawdown_pct: float = 8.0         # Kill switch at 8% drawdown
    max_positions: int = 1                # Only 1 position at a time
    max_position_size_lots: float = 0.05  # Max 0.05 lot (5 oz) for paper testing
    units_per_lot: float = 100.0
    
    # === DYNAMIC SL/TP (1:2 Risk/Reward) ===
    sl_distance_points: float = 37.0   # SL distance in price points (35-40 range)
    risk_reward_ratio: float = 2.0     # TP = SL distance * 2
    
    # === BREAKEVEN ===
    breakeven_trigger_pips: float = 30.0  # Move SL to BE after 30 pips profit
    trailing_stop_pips: float = 50.0
    
    # === AI VALIDATION ===
    ai_validation_enabled: bool = True
    ai_model: str = "claude-sonnet-4-20250514"
    ai_min_confidence: float = 0.6
    
    # === MT5 ===
    mt5_login: int = 0
    mt5_password: str = ""
    mt5_server: str = "Pepperstone-Demo"
    mt5_path: str = r"C:\Program Files\Pepperstone MetaTrader 5\terminal64.exe"
    mt5_timeout_ms: int = 60000
    
    # === TELEGRAM ===
    telegram_bot_token: str = ""
    telegram_chat_id: str = ""
    
    # === STRATEGY WEIGHTS ===
    strategy_weights: dict = field(default_factory=lambda: {
        "order_block": 1.2,
        "supply_demand": 1.1,
        "ema_cross": 1.0,
        "rsi_divergence": 1.0,
        "london_breakout": 1.1,
        "fibonacci": 1.0,
        "vwap_rejection": 1.0,
        "news_fade": 0.9,
        "multi_tf_align": 1.2,
        "bos_choch": 1.1,
        "liquidity_sweep": 1.3,
        "fair_value_gap": 1.2,
        "opening_range": 1.1,
    })
    
    def __post_init__(self):
        """Load from environment variables"""
        self.mt5_login = int(os.getenv("MT5_LOGIN", self.mt5_login))
        self.mt5_password = os.getenv("MT5_PASSWORD", self.mt5_password)
        self.mt5_server = os.getenv("MT5_SERVER", self.mt5_server)
        self.mt5_path = os.getenv("MT5_PATH", self.mt5_path)
        self.mt5_timeout_ms = int(os.getenv("MT5_TIMEOUT_MS", self.mt5_timeout_ms))
        self.telegram_bot_token = os.getenv("TELEGRAM_BOT_TOKEN", self.telegram_bot_token)
        self.telegram_chat_id = os.getenv("TELEGRAM_CHAT_ID", self.telegram_chat_id)
    
    def get_mode_risk_limits(self) -> dict:
        """Get risk limits"""
        return {
            "max_risk_per_trade_pct": self.max_risk_per_trade_pct,
            "max_daily_loss_pct": self.max_daily_loss_pct,
            "max_positions": self.max_positions,
        }


# Global config
_config: Optional[BotConfig] = None


def get_bot_config() -> BotConfig:
    """Get or create global config"""
    global _config
    if _config is None:
        _config = BotConfig()
    return _config
