"""
Live Data Feed - Real-time market data for paper and live trading

Supports:
- MT5 real-time ticks and bars
- Yahoo Finance (for backtesting/delayed data)
- Fallback chain with health monitoring
"""

import asyncio
from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Optional, Dict, Any, List, Callable
import time


@dataclass
class Tick:
    """Real-time tick data"""
    symbol: str
    bid: Decimal
    ask: Decimal
    timestamp: datetime
    volume: float = 0.0

    @property
    def mid(self) -> Decimal:
        return (self.bid + self.ask) / 2

    @property
    def spread(self) -> Decimal:
        return self.ask - self.bid


@dataclass
class Bar:
    """OHLCV bar"""
    symbol: str
    timestamp: datetime
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    volume: float


class DataFeed(ABC):
    """Abstract base class for data feeds"""

    def __init__(self, name: str):
        self.name = name
        self._connected = False
        self._callbacks: List[Callable] = []

    @abstractmethod
    async def connect(self) -> bool:
        pass

    @abstractmethod
    async def disconnect(self) -> None:
        pass

    @abstractmethod
    async def get_tick(self, symbol: str) -> Optional[Tick]:
        pass

    @abstractmethod
    async def get_bars(
        self, symbol: str, timeframe: str, count: int
    ) -> List[Bar]:
        pass

    def on_tick(self, callback: Callable):
        """Register tick callback"""
        self._callbacks.append(callback)

    @property
    def is_connected(self) -> bool:
        return self._connected


class MT5DataFeed(DataFeed):
    """MetaTrader 5 real-time data feed"""

    def __init__(self, config=None):
        super().__init__("MT5")
        self.config = config
        self._mt5 = None
        self._tick_stream_task = None
        self._subscribed_symbols: set = set()

    async def connect(self) -> bool:
        """Connect to MT5 terminal"""
        try:
            import MetaTrader5 as mt5
            self._mt5 = mt5

            if not mt5.initialize():
                print("MT5 initialization failed")
                return False

            account = mt5.account_info()
            if account is None:
                print("Failed to get MT5 account info")
                return False

            self._connected = True
            print(f"MT5 connected: {account.login} @ {account.server}")
            return True

        except ImportError:
            print("MetaTrader5 package not installed")
            return False
        except Exception as e:
            print(f"MT5 connection error: {e}")
            return False

    async def disconnect(self) -> None:
        """Disconnect from MT5"""
        if self._tick_stream_task:
            self._tick_stream_task.cancel()
        if self._mt5:
            self._mt5.shutdown()
        self._connected = False

    async def get_tick(self, symbol: str) -> Optional[Tick]:
        """Get latest tick for symbol"""
        if not self._connected or not self._mt5:
            return None

        try:
            tick = self._mt5.symbol_info_tick(symbol)
            if tick is None:
                return None

            return Tick(
                symbol=symbol,
                bid=Decimal(str(tick.bid)),
                ask=Decimal(str(tick.ask)),
                timestamp=datetime.fromtimestamp(tick.time),
                volume=tick.volume_real if hasattr(tick, 'volume_real') else 0,
            )
        except Exception as e:
            print(f"MT5 tick error for {symbol}: {e}")
            return None

    async def get_bars(
        self, symbol: str, timeframe: str, count: int
    ) -> List[Bar]:
        """Get historical bars from MT5"""
        if not self._connected or not self._mt5:
            return []

        tf_map = {
            "M1": self._mt5.TIMEFRAME_M1,
            "M5": self._mt5.TIMEFRAME_M5,
            "M15": self._mt5.TIMEFRAME_M15,
            "M30": self._mt5.TIMEFRAME_M30,
            "H1": self._mt5.TIMEFRAME_H1,
            "H4": self._mt5.TIMEFRAME_H4,
            "D1": self._mt5.TIMEFRAME_D1,
        }

        tf = tf_map.get(timeframe.upper(), self._mt5.TIMEFRAME_M15)

        try:
            rates = self._mt5.copy_rates_from_pos(symbol, tf, 0, count)
            if rates is None or len(rates) == 0:
                return []

            bars = []
            for r in rates:
                bars.append(Bar(
                    symbol=symbol,
                    timestamp=datetime.fromtimestamp(r["time"]),
                    open=Decimal(str(r["open"])),
                    high=Decimal(str(r["high"])),
                    low=Decimal(str(r["low"])),
                    close=Decimal(str(r["close"])),
                    volume=float(r["tick_volume"]),
                ))

            return bars

        except Exception as e:
            print(f"MT5 bars error for {symbol}: {e}")
            return []

    def start_tick_stream(self, symbols: List[str]) -> None:
        """Start streaming ticks in background"""
        self._subscribed_symbols = set(symbols)
        self._tick_stream_task = asyncio.create_task(self._stream_ticks())

    async def _stream_ticks(self) -> None:
        """Background task to stream ticks"""
        while self._connected:
            for symbol in self._subscribed_symbols:
                tick = await self.get_tick(symbol)
                if tick:
                    for callback in self._callbacks:
                        try:
                            await callback(tick) if asyncio.iscoroutinefunction(callback) else callback(tick)
                        except Exception as e:
                            print(f"Tick callback error: {e}")

            await asyncio.sleep(0.1)  # 100ms polling


class YahooDataFeed(DataFeed):
    """Yahoo Finance data feed (delayed, for backtesting)"""

    def __init__(self):
        super().__init__("Yahoo")
        self._cache: Dict[str, List[Bar]] = {}

    async def connect(self) -> bool:
        """Yahoo doesn't need connection"""
        self._connected = True
        return True

    async def disconnect(self) -> None:
        self._connected = False

    async def get_tick(self, symbol: str) -> Optional[Tick]:
        """Yahoo doesn't provide real-time ticks, get last bar"""
        bars = await self.get_bars(symbol, "M1", 1)
        if bars:
            last = bars[-1]
            return Tick(
                symbol=symbol,
                bid=last.close,
                ask=last.close * Decimal("1.0002"),  # Simulate spread
                timestamp=last.timestamp,
            )
        return None

    async def get_bars(
        self, symbol: str, timeframe: str, count: int
    ) -> List[Bar]:
        """Get bars from Yahoo Finance"""
        try:
            import yfinance as yf
        except ImportError:
            return []

        # Map timeframe
        tf_map = {
            "M1": "1m", "M5": "5m", "M15": "15m", "M30": "30m",
            "H1": "1h", "H4": "1h", "D1": "1d",
        }

        interval = tf_map.get(timeframe.upper(), "15m")

        # Yahoo limits: 1m=7d, 5m=60d, 15m=60d, 1h=730d, 1d=unlimited
        period_map = {
            "1m": "7d", "5m": "60d", "15m": "60d",
            "30m": "60d", "1h": "730d", "1d": "5y",
        }
        period = period_map.get(interval, "60d")

        try:
            ticker = yf.Ticker(symbol)
            df = ticker.history(period=period, interval=interval)

            if df.empty:
                return []

            # Take last N bars
            df = df.tail(count)

            bars = []
            for idx, row in df.iterrows():
                bars.append(Bar(
                    symbol=symbol,
                    timestamp=idx.to_pydatetime(),
                    open=Decimal(str(row["Open"])),
                    high=Decimal(str(row["High"])),
                    low=Decimal(str(row["Low"])),
                    close=Decimal(str(row["Close"])),
                    volume=float(row["Volume"]),
                ))

            return bars

        except Exception as e:
            print(f"Yahoo data error for {symbol}: {e}")
            return []


class DataFeedManager:
    """
    Manages multiple data feeds with fallback chain.

    Priority: MT5 > Yahoo
    """

    def __init__(self):
        self.feeds: List[DataFeed] = []
        self._active_feed: Optional[DataFeed] = None
        self._health: Dict[str, Dict] = {}

    def add_feed(self, feed: DataFeed, priority: int = 0) -> None:
        """Add a data feed with priority (lower = higher priority)"""
        self.feeds.append((priority, feed))
        self.feeds.sort(key=lambda x: x[0])
        self._health[feed.name] = {"last_check": time.time(), "errors": 0, "ok": True}

    async def connect(self) -> bool:
        """Connect to the highest priority available feed"""
        for _, feed in self.feeds:
            try:
                if await feed.connect():
                    self._active_feed = feed
                    print(f"Data feed connected: {feed.name}")
                    return True
            except Exception as e:
                print(f"Failed to connect {feed.name}: {e}")
                continue

        return False

    async def get_tick(self, symbol: str) -> Optional[Tick]:
        """Get tick from active feed — fail-loud if all sources fail"""
        errors = []
        for _, feed in self.feeds:
            if not feed.is_connected:
                continue

            try:
                tick = await feed.get_tick(symbol)
                if tick:
                    self._health[feed.name]["last_check"] = time.time()
                    self._health[feed.name]["errors"] = 0
                    return tick
            except Exception as e:
                self._health[feed.name]["errors"] += 1
                errors.append(f"{feed.name}: {e}")
                if self._health[feed.name]["errors"] > 5:
                    self._health[feed.name]["ok"] = False
                continue

        # FAIL-LOUD: all sources failed
        if errors:
            raise ConnectionError(
                f"All data feeds failed for {symbol}:\n" + "\n".join(errors)
            )
        return None

    async def get_bars(
        self, symbol: str, timeframe: str, count: int
    ) -> List[Bar]:
        """Get bars from active feed — fail-loud if all sources fail"""
        errors = []
        for _, feed in self.feeds:
            if not feed.is_connected:
                continue

            try:
                bars = await feed.get_bars(symbol, timeframe, count)
                if bars:
                    self._health[feed.name]["last_check"] = time.time()
                    self._health[feed.name]["errors"] = 0
                    return bars
            except Exception as e:
                self._health[feed.name]["errors"] += 1
                errors.append(f"{feed.name}: {e}")
                continue

        # FAIL-LOUD: all sources failed
        if errors:
            raise ConnectionError(
                f"All data feeds failed for {symbol} {timeframe}:\n" + "\n".join(errors)
            )
        return []

        return []

    async def health_check(self) -> Dict[str, Any]:
        """Check health of all feeds"""
        result = {}
        for _, feed in self.feeds:
            health = self._health.get(feed.name, {})
            result[feed.name] = {
                "connected": feed.is_connected,
                "is_active": feed == self._active_feed,
                "last_check": health.get("last_check", 0),
                "errors": health.get("errors", 0),
                "healthy": health.get("ok", False),
            }
        return result

    def start_streaming(self, symbols: List[str]) -> None:
        """Start tick streaming on active feed"""
        if self._active_feed and hasattr(self._active_feed, 'start_tick_stream'):
            self._active_feed.start_tick_stream(symbols)
