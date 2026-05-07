"""
Risk Engine for the trading system.
Enforces strict risk management rules, including Hard Rule 08 (Stop loss > 2%).
"""

import logging
from typing import Dict, Any

logger = logging.getLogger(__name__)

class RiskEngine:
    """Enforces trading risk rules."""

    # Hard Rule 08: Maximum allowable drawdown is 2% of initial capital
    MAX_DRAWDOWN_PCT = 0.02 

    def __init__(self, initial_capital: float = 100000.0):
        self.initial_capital = initial_capital
        self.current_capital = initial_capital
        self.cumulative_pnl = 0.0

    def update_pnl(self, realized_pnl: float) -> None:
        """
        Update cumulative PnL and current capital from a closed trade.
        """
        self.cumulative_pnl += realized_pnl
        self.current_capital += realized_pnl
        logger.info(
            f"PnL Updated: {realized_pnl:.2f}. "
            f"Cumulative PnL: {self.cumulative_pnl:.2f}. "
            f"Current Capital: {self.current_capital:.2f}"
        )

    def evaluate_risk(self) -> bool:
        """
        Evaluates current risk against Hard Rule 08.
        Returns False if trading should be HALTED (Hard Stop). Returns True if SAFE.
        """
        drawdown = self.initial_capital - self.current_capital
        drawdown_pct = drawdown / self.initial_capital if self.initial_capital > 0 else 0
        
        if drawdown_pct > self.MAX_DRAWDOWN_PCT:
            logger.critical(
                f"🚨 HARD STOP TRIGGERED 🚨: Current drawdown of {drawdown_pct*100:.2f}% "
                f"exceeds the hard limit of {self.MAX_DRAWDOWN_PCT*100:.2f}%!"
            )
            return False # Halt all trading
            
        logger.debug(f"Risk Check Passed: Current drawdown is {max(0, drawdown_pct)*100:.2f}%.")
        return True # Safe to trade

    def enforce_trade(self, proposed_trade: Dict[str, Any]) -> bool:
        """
        Checks if a specific proposed trade is allowed given the current risk state.
        """
        if not self.evaluate_risk():
            logger.warning(f"Trade REJECTED by Risk Engine due to Hard Stop: {proposed_trade}")
            return False
            
        # Additional per-trade risk checks (e.g. position sizing, exposure limits)
        # could be implemented here.
        logger.info(f"Trade APPROVED by Risk Engine: {proposed_trade}")
        return True
