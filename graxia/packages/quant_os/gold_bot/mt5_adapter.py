"""
MT5 adapter for Linux using yfinance.
Provides the same interface as MetaTrader5 Python package.
"""
import time
from datetime import datetime, timedelta
from typing import Optional
import yfinance as yf

# Map MT5 timeframe constants to yfinance periods
TIMEFRAME_M1 = "1m"
TIMEFRAME_M5 = "5m"
TIMEFRAME_M15 = "15m"
TIMEFRAME_M30 = "30m"
TIMEFRAME_H1 = "1h"
TIMEFRAME_H4 = "4h"
TIMEFRAME_D1 = "1d"

# Symbol mapping: MT5 symbol -> yfinance ticker
SYMBOL_MAP = {
    "XAUUSD": "GC=F",
    "EURUSD": "EURUSD=X",
    "BTCUSD": "BTC-USD",
    "GBPUSD": "GBPUSD=X",
    "USDJPY": "USDJPY=X",
    "USDCHF": "USDCHF=X",
    "AUDUSD": "AUDUSD=X",
    "USDCAD": "USDCAD=X",
}

# Point values (pip sizes)
POINT_MAP = {
    "XAUUSD": 0.01,
    "EURUSD": 0.00001,
    "BTCUSD": 0.01,
    "GBPUSD": 0.00001,
    "USDJPY": 0.001,
    "USDCHF": 0.00001,
    "AUDUSD": 0.00001,
    "USDCAD": 0.00001,
}

# Spread defaults (in points)
SPREAD_MAP = {
    "XAUUSD": 23,
    "EURUSD": 10,
    "BTCUSD": 1500,
    "GBPUSD": 12,
    "USDJPY": 11,
    "USDCHF": 14,
    "AUDUSD": 12,
    "USDCAD": 14,
}

TIMEFRAME_MAP = {
    "M1": TIMEFRAME_M1,
    "M5": TIMEFRAME_M5,
    "M15": TIMEFRAME_M15,
    "M30": TIMEFRAME_M30,
    "H1": TIMEFRAME_H1,
    "H4": TIMEFRAME_H4,
    "D1": TIMEFRAME_D1,
}


class SymbolInfo:
    def __init__(self, name: str):
        self.name = name
        self.point = POINT_MAP.get(name, 0.01)
        self.spread = SPREAD_MAP.get(name, 20)
        self._bid = 0.0
        self._ask = 0.0
        self._last_update = 0

    @property
    def bid(self):
        self._refresh()
        return self._bid

    @property
    def ask(self):
        self._refresh()
        return self._ask

    def _refresh(self):
        now = time.time()
        if now - self._last_update < 5:
            return
        try:
            ticker = SYMBOL_MAP.get(self.name)
            if ticker:
                t = yf.Ticker(ticker)
                info = t.fast_info
                self._bid = info.last_price
                spread_pts = SPREAD_MAP.get(self.name, 20)
                self._ask = self._bid + (spread_pts * self.point)
                self._last_update = now
        except Exception:
            pass


class AccountInfo:
    def __init__(self, balance: float = 50000.0):
        self.balance = balance
        self.equity = balance
        self.margin = 0.0
        self.free_margin = balance
        self.profit = 0.0
        self.leverage = 100


class Rates:
    def __init__(self, time, open, high, low, close, tick_volume, spread, real_volume):
        self.time = time
        self.open = open
        self.high = high
        self.low = low
        self.close = close
        self.tick_volume = tick_volume
        self.spread = spread
        self.real_volume = real_volume


class OrderSendResult:
    def __init__(self, retcode=10009, deal=0, order=0, comment="OK"):
        self.retcode = retcode
        self.deal = deal
        self.order = order
        self.comment = comment


class MT5Connection:
    def __init__(self):
        self._connected = False
        self._account_info = AccountInfo()
        self._symbols = {}

    def initialize(self, path=None, login=None, password=None, server=None, timeout=0, portable=False):
        self._connected = True
        return True

    def shutdown(self):
        self._connected = False

    def account_info(self):
        if not self._connected:
            return None
        return self._account_info

    def symbol_info(self, symbol: str) -> Optional[SymbolInfo]:
        if not self._connected:
            return None
        if symbol not in self._symbols:
            self._symbols[symbol] = SymbolInfo(symbol)
        return self._symbols[symbol]

    def copy_rates_from_pos(self, symbol: str, timeframe: str, start_pos: int, count: int):
        if not self._connected:
            return None

        ticker = SYMBOL_MAP.get(symbol)
        if not ticker:
            return None

        yf_tf = TIMEFRAME_MAP.get(timeframe, TIMEFRAME_M15)

        # Calculate period needed
        if count > 500:
            period = "60d"
        elif count > 200:
            period = "30d"
        elif count > 50:
            period = "7d"
        else:
            period = "2d"

        try:
            t = yf.Ticker(ticker)
            hist = t.history(period=period, interval=yf_tf)

            if hist.empty:
                return None

            # Take the last 'count' bars, skip start_pos
            total = len(hist)
            start_idx = max(0, total - count - start_pos)
            end_idx = min(total, total - start_pos)

            if start_idx >= end_idx:
                return None

            bars = []
            for i in range(start_idx, end_idx):
                row = hist.iloc[i]
                dt_idx = hist.index[i]
                timestamp = int(dt_idx.timestamp())
                bars.append(Rates(
                    time=timestamp,
                    open=float(row["Open"]),
                    high=float(row["High"]),
                    low=float(row["Low"]),
                    close=float(row["Close"]),
                    tick_volume=int(row.get("Volume", 0)),
                    spread=SPREAD_MAP.get(symbol, 20),
                    real_volume=0,
                ))

            return bars

        except Exception as e:
            print(f"copy_rates_from_pos error: {e}", flush=True)
            return None

    def order_send(self, request) -> OrderSendResult:
        return OrderSendResult(retcode=10009, comment="Paper mode")


def initialize(path=None, login=None, password=None, server=None, timeout=0, portable=False):
    conn = MT5Connection()
    return conn.initialize(path=path, login=login, password=password, server=server, timeout=timeout, portable=portable)
