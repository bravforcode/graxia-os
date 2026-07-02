"""Strategy lifecycle hooks from Freqtrade pattern"""

from abc import ABC
from datetime import datetime


class StrategyLifecycle(ABC):
    """Mixin that adds lifecycle hooks to strategies"""

    def bot_start(self) -> None:
        """Called once after initialization"""
        pass

    def bot_loop_start(self, current_time: datetime) -> None:
        """Called at start of each trading cycle"""
        pass

    def confirm_trade_entry(self, symbol: str, signal_type: str, amount: float, price: float) -> bool:
        """Final gate before execution. Return False to cancel."""
        return True

    def confirm_trade_exit(self, symbol: str, trade_id: str, exit_reason: str) -> bool:
        """Final gate before exit. Return False to cancel."""
        return True

    def on_trade_open(self, symbol: str, order_id: str) -> None:
        """Called when a trade is opened"""
        pass

    def on_trade_close(self, symbol: str, order_id: str, pnl: float) -> None:
        """Called when a trade is closed"""
        pass
