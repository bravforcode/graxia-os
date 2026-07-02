"""
MT5 Read-Only Client - Safe wrapper around MetaTrader 5.

Phase 3.2: Only exposes read-only operations.
Blocks order_send, order_modify, order_close at the wrapper level.
Every method wraps MT5 calls in try/except.
"""

from datetime import datetime

# ponytail: lazy-import pattern from broker/mt5_gateway.py
_mt5_imported = False
_mt5 = None


class Mt5UnavailableError(Exception):
    """Raised when MT5 terminal is not available."""
    pass


def _get_mt5():
    """Lazy-import MetaTrader5 package. Raises Mt5UnavailableError if unavailable."""
    global _mt5_imported, _mt5
    if _mt5_imported:
        if _mt5 is None:
            raise Mt5UnavailableError("MetaTrader5 package not installed")
        return _mt5
    _mt5_imported = True
    try:
        import MetaTrader5 as mt5
        _mt5 = mt5
        return mt5
    except ImportError:
        _mt5 = None
        raise Mt5UnavailableError(
            "MetaTrader5 package not installed. "
            "Install with: pip install MetaTrader5"
        )


class Mt5ReadOnlyClient:
    """
    Read-only wrapper around MetaTrader 5 API.

    CRITICAL CONSTRAINT: This client NEVER submits orders.
    order_send, order_modify, order_close are blocked at the class level.
    """

    def __init__(self):
        self._initialized = False

    def initialize(self, config: dict | None = None) -> bool:
        """
        Initialize MT5 terminal connection.

        Args:
            config: Optional dict with keys: path, timeout_ms

        Returns:
            True if initialization succeeded.

        Raises:
            Mt5UnavailableError: If MT5 is unreachable or init fails.
        """
        mt5 = _get_mt5()
        path = config.get("path", "") if config else ""
        timeout_ms = config.get("timeout_ms", 10000) if config else 10000
        try:
            kwargs = {}
            if path:
                kwargs["path"] = path
            kwargs["timeout"] = timeout_ms
            if not mt5.initialize(**kwargs):
                raise Mt5UnavailableError(f"MT5 init failed: {mt5.last_error()}")
            self._initialized = True
            return True
        except Mt5UnavailableError:
            raise
        except Exception as e:
            raise Mt5UnavailableError(f"MT5 initialization error: {e}") from e

    def _ensure_initialized(self):
        """Guard: raise if not connected."""
        if not self._initialized:
            raise Mt5UnavailableError("MT5 not initialized. Call initialize() first.")

    def get_terminal_info(self) -> dict:
        """
        Get MT5 terminal information.

        Returns:
            dict with terminal name, version, build, connected status, etc.
        """
        self._ensure_initialized()
        mt5 = _get_mt5()
        try:
            info = mt5.terminal_info()
            if info is None:
                raise Mt5UnavailableError("Could not get terminal info")
            return {
                "name": info.name,
                "path": info.path,
                "community_account": info.community_account,
                "community_connection": info.community_connection,
                "connected": info.connected,
                "dlls_allowed": info.dlls_allowed,
                "trade_allowed": info.trade_allowed,
                "ftp_enabled": info.ftp_enabled,
                "notifications_enabled": info.notifications_enabled,
                "max_bars": info.max_bars,
                "build": info.build,
                "display_depth": info.display_depth,
            }
        except Mt5UnavailableError:
            raise
        except Exception as e:
            raise Mt5UnavailableError(f"Terminal info error: {e}") from e

    def get_account_info_redacted(self) -> dict:
        """
        Get account info with account number masked.

        Account number is redacted to show only last 4 digits.
        All values read from MT5, never computed.
        """
        self._ensure_initialized()
        mt5 = _get_mt5()
        try:
            info = mt5.account_info()
            if info is None:
                raise Mt5UnavailableError("Could not get account info")

            login_str = str(info.login)
            if len(login_str) > 4:
                redacted = "*" * (len(login_str) - 4) + login_str[-4:]
            else:
                redacted = login_str

            return {
                "login_redacted": redacted,
                "server": info.server or "",
                "currency": info.currency or "USD",
                "balance": float(info.balance),
                "equity": float(info.equity),
                "margin": float(info.margin),
                "margin_free": float(info.margin_free),
                "margin_level": float(info.margin_level) if info.margin_level else None,
                "leverage": info.leverage,
                "profit": float(info.profit),
                "name": info.name or "",
                "company": info.company or "",
            }
        except Mt5UnavailableError:
            raise
        except Exception as e:
            raise Mt5UnavailableError(f"Account info error: {e}") from e

    def get_symbol_info(self, symbol: str) -> dict:
        """
        Get full symbol specification.

        Args:
            symbol: Trading symbol (e.g. "XAUUSD").
        """
        self._ensure_initialized()
        mt5 = _get_mt5()
        try:
            info = mt5.symbol_info(symbol)
            if info is None:
                raise Mt5UnavailableError(f"Could not get symbol info for {symbol}")
            return {
                "name": info.name,
                "digits": info.digits,
                "point": float(info.point),
                "spread": info.spread,
                "spread_float": info.spread_float,
                "volume_min": float(info.volume_min),
                "volume_max": float(info.volume_max),
                "volume_step": float(info.volume_step),
                "trade_contract_size": float(info.trade_contract_size),
                "trade_tick_size": float(info.trade_tick_size),
                "trade_tick_value": float(info.trade_tick_value),
                "stops_level": info.stops_level,
                "freeze_level": info.freeze_level,
                "trade_mode": info.trade_mode,
                "filling_mode": info.filling_mode,
                "execution_mode": info.execution_mode,
                "currency_base": info.currency_base or "",
                "currency_profit": info.currency_profit or "",
                "currency_margin": info.currency_margin or "",
            }
        except Mt5UnavailableError:
            raise
        except Exception as e:
            raise Mt5UnavailableError(f"Symbol info error for {symbol}: {e}") from e

    def get_symbol_info_tick(self, symbol: str) -> dict:
        """
        Get current bid/ask tick for a symbol.

        Args:
            symbol: Trading symbol (e.g. "XAUUSD").
        """
        self._ensure_initialized()
        mt5 = _get_mt5()
        try:
            tick = mt5.symbol_info_tick(symbol)
            if tick is None:
                raise Mt5UnavailableError(f"Could not get tick for {symbol}")
            return {
                "bid": float(tick.bid),
                "ask": float(tick.ask),
                "last": float(tick.last),
                "volume": float(tick.volume),
                "time": tick.time,
                "time_msc": tick.time_msc,
                "flags": tick.flags,
            }
        except Mt5UnavailableError:
            raise
        except Exception as e:
            raise Mt5UnavailableError(f"Tick error for {symbol}: {e}") from e

    def copy_ticks_range(
        self, symbol: str, start: datetime, end: datetime, flags: int = 16
    ) -> list[dict]:
        """
        Copy a range of ticks for a symbol.

        Args:
            symbol: Trading symbol.
            start: Start datetime.
            end: End datetime.
            flags: MT5 copy ticks flags (default: COPY_TICKS_ALL = 16).

        Returns:
            List of tick dicts.
        """
        self._ensure_initialized()
        mt5 = _get_mt5()
        try:
            ticks = mt5.copy_ticks_range(symbol, start, end, flags)
            if ticks is None:
                raise Mt5UnavailableError(
                    f"Could not copy ticks for {symbol} from {start} to {end}"
                )
            result = []
            for t in ticks:
                result.append({
                    "bid": float(t.bid),
                    "ask": float(t.ask),
                    "last": float(t.last),
                    "volume": float(t.volume),
                    "time": t.time,
                    "time_msc": t.time_msc,
                    "flags": t.flags,
                })
            return result
        except Mt5UnavailableError:
            raise
        except Exception as e:
            raise Mt5UnavailableError(f"Copy ticks error for {symbol}: {e}") from e

    def get_bars(self, symbol: str, timeframe: int, count: int) -> list[dict]:
        """
        Get OHLCV bars.

        Args:
            symbol: Trading symbol.
            timeframe: MT5 timeframe constant (e.g. mt5.TIMEFRAME_H1).
            count: Number of bars to retrieve.

        Returns:
            List of OHLCV dicts.
        """
        self._ensure_initialized()
        mt5 = _get_mt5()
        try:
            rates = mt5.copy_rates_from_pos(symbol, timeframe, 0, count)
            if rates is None:
                raise Mt5UnavailableError(
                    f"Could not get bars for {symbol} timeframe={timeframe}"
                )
            result = []
            for r in rates:
                result.append({
                    "time": r["time"],
                    "open": float(r["open"]),
                    "high": float(r["high"]),
                    "low": float(r["low"]),
                    "close": float(r["close"]),
                    "tick_volume": int(r["tick_volume"]),
                    "spread": int(r["spread"]),
                    "real_volume": int(r["real_volume"]),
                })
            return result
        except Mt5UnavailableError:
            raise
        except Exception as e:
            raise Mt5UnavailableError(f"Get bars error for {symbol}: {e}") from e

    def get_positions(self) -> list[dict]:
        """Get all open positions."""
        self._ensure_initialized()
        mt5 = _get_mt5()
        try:
            positions = mt5.positions_get()
            if positions is None:
                return []
            result = []
            for p in positions:
                result.append({
                    "ticket": p.ticket,
                    "time": p.time,
                    "time_msc": p.time_msc,
                    "time_update": p.time_update,
                    "time_update_msc": p.time_update_msc,
                    "type": p.type,
                    "magic": p.magic,
                    "identifier": p.identifier,
                    "reason": p.reason,
                    "volume": float(p.volume),
                    "price_open": float(p.price_open),
                    "sl": float(p.sl),
                    "tp": float(p.tp),
                    "price_current": float(p.price_current),
                    "swap": float(p.swap),
                    "profit": float(p.profit),
                    "commission": float(p.commission) if hasattr(p, "commission") else 0.0,
                    "symbol": p.symbol,
                    "comment": p.comment or "",
                })
            return result
        except Mt5UnavailableError:
            raise
        except Exception as e:
            raise Mt5UnavailableError(f"Get positions error: {e}") from e

    def get_orders(self) -> list[dict]:
        """Get all active pending orders."""
        self._ensure_initialized()
        mt5 = _get_mt5()
        try:
            orders = mt5.orders_get()
            if orders is None:
                return []
            result = []
            for o in orders:
                result.append({
                    "ticket": o.ticket,
                    "time_setup": o.time_setup,
                    "time_expiration": o.time_expiration,
                    "type": o.type,
                    "type_filling": o.type_filling,
                    "type_time": o.type_time,
                    "magic": o.magic,
                    "volume_current": float(o.volume_current),
                    "volume_initial": float(o.volume_initial),
                    "price_open": float(o.price_open),
                    "sl": float(o.sl),
                    "tp": float(o.tp),
                    "price_current": float(o.price_current),
                    "symbol": o.symbol,
                    "comment": o.comment or "",
                })
            return result
        except Mt5UnavailableError:
            raise
        except Exception as e:
            raise Mt5UnavailableError(f"Get orders error: {e}") from e

    def get_history_orders(
        self,
        start: datetime | None = None,
        end: datetime | None = None,
        group: str = "",
    ) -> list[dict]:
        """
        Get historical orders.

        Args:
            start: Start of range (optional).
            end: End of range (optional).
            group: Symbol group filter (e.g. "*USD*" for all USD pairs).
        """
        self._ensure_initialized()
        mt5 = _get_mt5()
        try:
            kwargs = {}
            if start is not None:
                kwargs["start"] = start
            if end is not None:
                kwargs["end"] = end
            if group:
                kwargs["group"] = group
            orders = mt5.history_orders_get(**kwargs)
            if orders is None:
                return []
            result = []
            for o in orders:
                result.append({
                    "ticket": o.ticket,
                    "time_setup": o.time_setup,
                    "time_setup_msc": o.time_setup_msc,
                    "time_done": o.time_done,
                    "time_done_msc": o.time_done_msc,
                    "type": o.type,
                    "type_filling": o.type_filling,
                    "type_time": o.type_time,
                    "magic": o.magic,
                    "volume_current": float(o.volume_current),
                    "volume_initial": float(o.volume_initial),
                    "price_open": float(o.price_open),
                    "sl": float(o.sl),
                    "tp": float(o.tp),
                    "price_current": float(o.price_current),
                    "symbol": o.symbol,
                    "comment": o.comment or "",
                    "retcode": o.retcode,
                    "status": o.status,
                })
            return result
        except Mt5UnavailableError:
            raise
        except Exception as e:
            raise Mt5UnavailableError(f"Get history orders error: {e}") from e

    def get_history_deals(
        self,
        start: datetime | None = None,
        end: datetime | None = None,
        group: str = "",
    ) -> list[dict]:
        """
        Get historical deals.

        Args:
            start: Start of range (optional).
            end: End of range (optional).
            group: Symbol group filter.
        """
        self._ensure_initialized()
        mt5 = _get_mt5()
        try:
            kwargs = {}
            if start is not None:
                kwargs["start"] = start
            if end is not None:
                kwargs["end"] = end
            if group:
                kwargs["group"] = group
            deals = mt5.history_deals_get(**kwargs)
            if deals is None:
                return []
            result = []
            for d in deals:
                result.append({
                    "ticket": d.ticket,
                    "order": d.order,
                    "time": d.time,
                    "time_msc": d.time_msc,
                    "type": d.type,
                    "entry": d.entry,
                    "magic": d.magic,
                    "volume": float(d.volume),
                    "price": float(d.price),
                    "commission": float(d.commission),
                    "swap": float(d.swap),
                    "profit": float(d.profit),
                    "symbol": d.symbol,
                    "comment": d.comment or "",
                    "position_id": d.position_id,
                    "reason": d.reason,
                })
            return result
        except Mt5UnavailableError:
            raise
        except Exception as e:
            raise Mt5UnavailableError(f"Get history deals error: {e}") from e

    def order_calc_profit(
        self, symbol: str, volume: float, price: float
    ) -> float:
        """
        Calculate hypothetical profit for a buy order at given volume and price.

        This is a READ-ONLY calculation - no order is submitted.
        """
        self._ensure_initialized()
        mt5 = _get_mt5()
        try:
            result = mt5.order_calc_profit(mt5.ORDER_TYPE_BUY, symbol, volume, price)
            return float(result) if result is not None else 0.0
        except Exception as e:
            raise Mt5UnavailableError(
                f"Profit calc error for {symbol}: {e}"
            ) from e

    def order_calc_margin(
        self, symbol: str, volume: float, price: float
    ) -> float:
        """
        Calculate required margin for a buy order at given volume and price.

        This is a READ-ONLY calculation - no order is submitted.
        """
        self._ensure_initialized()
        mt5 = _get_mt5()
        try:
            result = mt5.order_calc_margin(mt5.ORDER_TYPE_BUY, symbol, volume, price)
            return float(result) if result is not None else 0.0
        except Exception as e:
            raise Mt5UnavailableError(
                f"Margin calc error for {symbol}: {e}"
            ) from e

    def order_check(self, request: dict) -> dict:
        """
        Validate an order request WITHOUT submitting it.

        This is purely a validation call - no order is ever sent to the broker.

        Args:
            request: Order request dict (same format as MT5 order_send).

        Returns:
            dict with retcode, comment, volume, price, bid, ask.
        """
        self._ensure_initialized()
        mt5 = _get_mt5()
        try:
            result = mt5.order_check(request)
            if result is None:
                return {"retcode": 0, "comment": "No result from MT5", "volume": 0.0}
            return {
                "retcode": result.retcode,
                "comment": result.comment,
                "volume": result.volume,
                "price": result.price,
                "bid": result.bid,
                "ask": result.ask,
            }
        except Mt5UnavailableError:
            raise
        except Exception as e:
            raise Mt5UnavailableError(f"Order check error: {e}") from e

    def shutdown(self):
        """Shutdown MT5 connection gracefully."""
        if not self._initialized:
            return
        mt5 = _get_mt5()
        try:
            mt5.shutdown()
        except Exception:
            pass  # best-effort shutdown
        finally:
            self._initialized = False


# === SAFETY ASSERTION ===
# This class must NEVER contain order_send, order_modify, or order_close.
_BLOCKED = ["order_send", "order_modify", "order_close"]
for _method in _BLOCKED:
    if hasattr(Mt5ReadOnlyClient, _method):
        raise RuntimeError(
            f"FORBIDDEN: {_method} must not exist in Mt5ReadOnlyClient"
        )
