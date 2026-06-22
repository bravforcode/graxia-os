"""
MT5 connection manager.

IMPORTANT: This module requires MetaTrader5 package (pip install MetaTrader5)
and a running MT5 terminal. It will NOT work without MT5 installed.

Usage:
    from mt5_connector.connection import MT5Connection
    
    conn = MT5Connection()
    if conn.connect():
        account = conn.get_account_info()
        conn.disconnect()
"""
from dataclasses import dataclass
from typing import Optional, Any
import logging

logger = logging.getLogger(__name__)

@dataclass
class MT5AccountInfo:
    login: int
    server: str
    balance: float
    equity: float
    margin: float
    free_margin: float
    leverage: int
    currency: str
    trade_allowed: bool

@dataclass
class MT5SymbolInfo:
    symbol: str
    bid: float
    ask: float
    spread: int
    point: float
    digits: int
    contract_size: float
    min_volume: float
    max_volume: float
    volume_step: float
    trade_allowed: bool

class MT5Connection:
    """Manages connection to MetaTrader 5 terminal."""
    
    def __init__(self):
        self._connected = False
        self._mt5 = None
    
    def connect(self, path: Optional[str] = None, timeout: int = 10000) -> bool:
        """Connect to MT5 terminal."""
        try:
            import MetaTrader5 as mt5
            self._mt5 = mt5
            
            if path:
                initialized = mt5.initialize(path=path, timeout=timeout)
            else:
                initialized = mt5.initialize(timeout=timeout)
            
            if not initialized:
                error = mt5.last_error()
                logger.error(f"MT5 initialize failed: {error}")
                return False
            
            self._connected = True
            logger.info("MT5 connected successfully")
            return True
            
        except ImportError:
            logger.error("MetaTrader5 package not installed. Run: pip install MetaTrader5")
            return False
        except Exception as e:
            logger.error(f"MT5 connection error: {e}")
            return False
    
    def disconnect(self) -> None:
        """Disconnect from MT5 terminal."""
        if self._mt5 and self._connected:
            self._mt5.shutdown()
            self._connected = False
            logger.info("MT5 disconnected")
    
    def is_connected(self) -> bool:
        return self._connected
    
    def get_account_info(self) -> Optional[MT5AccountInfo]:
        """Get current account information."""
        if not self._connected:
            return None
        
        info = self._mt5.account_info()
        if info is None:
            return None
        
        return MT5AccountInfo(
            login=info.login,
            server=info.server,
            balance=info.balance,
            equity=info.equity,
            margin=info.margin,
            free_margin=info.margin_free,
            leverage=info.leverage,
            currency=info.currency,
            trade_allowed=info.trade_allowed,
        )
    
    def get_symbol_info(self, symbol: str) -> Optional[MT5SymbolInfo]:
        """Get symbol specification."""
        if not self._connected:
            return None
        
        info = self._mt5.symbol_info(symbol)
        if info is None:
            return None
        
        return MT5SymbolInfo(
            symbol=info.name,
            bid=info.bid,
            ask=info.ask,
            spread=info.spread,
            point=info.point,
            digits=info.digits,
            contract_size=info.trade_contract_size,
            min_volume=info.volume_min,
            max_volume=info.volume_max,
            volume_step=info.volume_step,
            trade_allowed=info.visible,
        )
    
    def get_tick(self, symbol: str) -> Optional[dict]:
        """Get latest tick for symbol."""
        if not self._connected:
            return None
        
        tick = self._mt5.symbol_info_tick(symbol)
        if tick is None:
            return None
        
        return {
            "bid": tick.bid,
            "ask": tick.ask,
            "last": tick.last,
            "volume": tick.volume,
            "time": tick.time,
            "flags": tick.flags,
        }
    
    def get_bars(self, symbol: str, timeframe: int, count: int = 100) -> Optional[list]:
        """Get historical bars using date range (more reliable).
        
        timeframe: Use MT5 constants (mt5.TIMEFRAME_H1=16385, mt5.TIMEFRAME_D1=16408)
        or shortcuts: 1=M1, 5=M5, 15=M15, 30=M30, 60=H1, 240=H4, 1440=D1
        """
        if not self._connected:
            return None
        
        # Map simple integers to MT5 constants if needed
        tf_map = {
            1: self._mt5.TIMEFRAME_M1, 5: self._mt5.TIMEFRAME_M5,
            15: self._mt5.TIMEFRAME_M15, 30: self._mt5.TIMEFRAME_M30,
            60: self._mt5.TIMEFRAME_H1, 240: self._mt5.TIMEFRAME_H4,
            1440: self._mt5.TIMEFRAME_D1,
        }
        mt5_tf = tf_map.get(timeframe, timeframe)
        
        from datetime import timedelta, datetime as dt
        now = dt.utcnow()
        to = now
        # Estimate time range: count bars * timeframe in seconds
        fr = now - timedelta(seconds=count * 60 * 60)  # conservative estimate
        rates = self._mt5.copy_rates_range(symbol, mt5_tf, fr, to)
        if rates is None:
            return None
        
        return [
            {
                "time": int(r[0]),
                "open": r[1],
                "high": r[2],
                "low": r[3],
                "close": r[4],
                "volume": int(r[5]),
            }
            for r in rates
        ]
