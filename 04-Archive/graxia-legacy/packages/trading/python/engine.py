"""
Trading Engine for live and paper trading.
Integrates with Binance API and enforces risk management rules.
"""

import logging
import asyncio
import os
from typing import Dict, Any, Optional
from .risk_engine import RiskEngine

logger = logging.getLogger(__name__)

class TradingEngine:
    """Trading engine that handles live and paper trades."""

    def __init__(self, api_key: Optional[str] = None, api_secret: Optional[str] = None):
        self.api_key = api_key or os.getenv("BINANCE_API_KEY")
        self.api_secret = api_secret or os.getenv("BINANCE_API_SECRET")
        self.live_mode = os.getenv("LIVE_MODE") == "true"
        self.risk_engine = RiskEngine()
        self.ws_connected = False
        self.current_prices: Dict[str, float] = {}

    async def connect_ws(self, symbol: str):
        """Connect to Binance WebSocket for real-time market data."""
        mode_str = "LIVE" if self.live_mode else "SANDBOX"
        logger.info(f"Connecting to Binance WebSocket ({mode_str}) for {symbol}...")
        
        # Stub: Simulate network connection delay
        await asyncio.sleep(0.5) 
        self.ws_connected = True
        self.current_prices[symbol] = 50000.00 # Stub price
        
        logger.info(f"Connected to {mode_str} stream for {symbol}.")

    async def get_current_price(self, symbol: str) -> float:
        """Retrieve the latest price from the WebSocket stream."""
        return self.current_prices.get(symbol, 0.0)

    async def execute_trade(self, symbol: str, action: str, quantity: float) -> Dict[str, Any]:
        """
        Executes a trade. Checks risk limits before live execution.
        """
        price = await self.get_current_price(symbol)
        proposed_trade = {
            "symbol": symbol,
            "action": action,
            "quantity": quantity,
            "price": price,
            "live": self.live_mode
        }

        # Check Risk Engine before any live trade
        if self.live_mode:
            if not self.risk_engine.enforce_trade(proposed_trade):
                logger.warning(f"LIVE TRADE REJECTED: Risk check failed for {symbol}")
                return {"status": "REJECTED", "reason": "Risk Engine Limit"}

        if self.live_mode:
            return await self._execute_live_order(symbol, action, quantity, price)
        else:
            return await self._execute_paper_trade(symbol, action, quantity, price)

    async def _execute_live_order(self, symbol: str, action: str, quantity: float, price: float) -> Dict[str, Any]:
        """
        Internal method for real Binance API order placement.
        """
        logger.info(f"🚀 LIVE ORDER PLACEMENT: {action} {quantity} {symbol} @ market (~{price})")
        
        if not self.api_key:
            logger.error("Missing BINANCE_API_KEY for live trade.")
            return {"status": "FAILED", "reason": "Missing API Key"}

        # Stub for python-binance call:
        # client = AsyncClient(self.api_key, self.api_secret)
        # order = await client.create_order(symbol=symbol, side=action, type='MARKET', quantity=quantity)
        
        await asyncio.sleep(0.2) # Simulate network latency
        
        return {
            "status": "FILLED",
            "symbol": symbol,
            "action": action,
            "executed_quantity": quantity,
            "executed_price": price,
            "order_id": f"binance_live_{int(asyncio.get_event_loop().time())}",
            "is_paper_trade": False
        }

    async def _execute_paper_trade(self, symbol: str, action: str, quantity: float, price: float) -> Dict[str, Any]:
        """
        Simulate order execution for paper trading.
        """
        logger.info(f"PAPER TRADE EXECUTION: {action} {quantity} {symbol} @ {price}")
        
        return {
            "status": "FILLED",
            "symbol": symbol,
            "action": action,
            "executed_quantity": quantity,
            "executed_price": price,
            "order_id": f"sim_paper_{int(asyncio.get_event_loop().time())}",
            "is_paper_trade": True
        }
