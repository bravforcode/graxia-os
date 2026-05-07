"""
Quant OS - Forex Quantitative Trading System for Graxia OS

Risk-first, evidence-first automated trading system supporting:
- MT5 broker integration
- Paper trading → Live micro promotion
- 3-strategy ensemble (MTM, MRB, MLB)
- Kill switch and circuit breakers
- Anti-overfitting validation

Trading Mode State Machine:
    RESEARCH_ONLY → BACKTEST_ONLY → SHADOW_MODE → PAPER_TRADING → LIVE_MICRO → LIVE_LIMITED → LIVE_CONTROLLED

Core Principle: AI suggests, Risk approves, Human confirms (micro), System executes.
"""

__version__ = "1.0.0"
__author__ = "Graxia OS"

from .core.golden_rules import GOLDEN_RULES
from .core.enums import SystemState, TradingMode, OrderStatus, OrderSide, OrderType

__all__ = [
    "GOLDEN_RULES",
    "SystemState",
    "TradingMode", 
    "OrderStatus",
    "OrderSide",
    "OrderType",
]
