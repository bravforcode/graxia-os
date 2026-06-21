"""
MT5 Gateway - READ-ONLY interface to MetaTrader 5.

This module wraps MT5 Python API calls for reading market data,
account info, and contract specifications. It does NOT send orders.

All MT5 calls are wrapped in try/except and raise Mt5UnavailableError
if MT5 is not accessible.
"""

from datetime import datetime
from decimal import Decimal
from typing import Optional

from .contract_spec import ContractSpec, compute_snapshot_hash


class Mt5UnavailableError(Exception):
    """Raised when MT5 terminal is not available."""
    pass


# ponytail: module-level flag to avoid repeated import attempts
_mt5_imported = False
_mt5 = None


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


def initialize_mt5(path: str, timeout_ms: int = 10000) -> bool:
    """Initialize MT5 terminal. Returns True if successful."""
    mt5 = _get_mt5()
    try:
        if not mt5.initialize(path=path, timeout=timeout_ms):
            raise Mt5UnavailableError(f"MT5 init failed: {mt5.last_error()}")
        return True
    except Mt5UnavailableError:
        raise
    except Exception as e:
        raise Mt5UnavailableError(f"MT5 initialization error: {e}") from e


def get_contract_spec(
    symbol: str,
    broker: str = "",
    server: str = "",
) -> ContractSpec:
    """
    Read symbol_info() from MT5 and build ContractSpec.
    Raises Mt5UnavailableError if MT5 not initialized or symbol info is invalid.
    """
    mt5 = _get_mt5()
    try:
        info = mt5.symbol_info(symbol)
        if info is None:
            raise Mt5UnavailableError(f"Could not get symbol info for {symbol}")

        acct = mt5.account_info()
        if acct is None:
            raise Mt5UnavailableError("Could not get account info")

        now = datetime.utcnow()
        spec = ContractSpec(
            broker=broker or acct.server.split("-")[0] if acct.server else "",
            server=server or acct.server or "",
            symbol=symbol,
            account_currency=acct.currency or "USD",
            digits=info.digits,
            point=Decimal(str(info.point)),
            trade_contract_size=Decimal(str(info.trade_contract_size)),
            trade_tick_size=Decimal(str(info.trade_tick_size)),
            trade_tick_value=Decimal(str(info.trade_tick_value)),
            volume_min=Decimal(str(info.volume_min)),
            volume_max=Decimal(str(info.volume_max)),
            volume_step=Decimal(str(info.volume_step)),
            stops_level_points=info.stops_level,
            freeze_level_points=info.freeze_level,
            currency_base=info.currency_base or "",
            currency_profit=info.currency_profit or "",
            currency_margin=info.currency_margin or "",
            trade_mode=info.trade_mode,
            filling_mode=info.filling_mode,
            execution_mode=info.execution_mode,
            captured_at_utc=now,
            snapshot_hash="",  # placeholder, computed below
        )
        # Compute hash after all fields are set
        h = compute_snapshot_hash(spec)
        return ContractSpec(**{**spec.__dict__, "snapshot_hash": h})
    except Mt5UnavailableError:
        raise
    except Exception as e:
        raise Mt5UnavailableError(f"Failed to build ContractSpec for {symbol}: {e}") from e


def get_current_tick(symbol: str) -> dict:
    """Get current bid/ask via symbol_info_tick()."""
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
        }
    except Mt5UnavailableError:
        raise
    except Exception as e:
        raise Mt5UnavailableError(f"Tick error for {symbol}: {e}") from e


def calc_profit(
    symbol: str, side: str, volume: float, entry: float, exit_price: float
) -> Optional[float]:
    """Wrapper for order_calc_profit(). Returns None on error."""
    mt5 = _get_mt5()
    try:
        order_type = mt5.ORDER_TYPE_BUY if side.upper() == "BUY" else mt5.ORDER_TYPE_SELL
        result = mt5.order_calc_profit(order_type, symbol, volume, entry, exit_price)
        return float(result) if result is not None else None
    except Exception:
        return None


def calc_margin(symbol: str, volume: float, price: float) -> Optional[float]:
    """Wrapper for order_calc_margin(). Returns None on error."""
    mt5 = _get_mt5()
    try:
        result = mt5.order_calc_margin(mt5.ORDER_TYPE_BUY, symbol, volume, price)
        return float(result) if result is not None else None
    except Exception:
        return None


def check_order(order_request: dict) -> Optional[dict]:
    """Wrapper for order_check(). Returns None on error."""
    mt5 = _get_mt5()
    try:
        result = mt5.order_check(order_request)
        if result is None:
            return None
        return {
            "retcode": result.retcode,
            "comment": result.comment,
            "volume": result.volume,
            "price": result.price,
            "bid": result.bid,
            "ask": result.ask,
        }
    except Exception:
        return None


def get_account_info() -> dict:
    """Get account info: equity, balance, margin_level, currency, etc."""
    mt5 = _get_mt5()
    try:
        info = mt5.account_info()
        if info is None:
            raise Mt5UnavailableError("Could not get account info")
        return {
            "login": info.login,
            "server": info.server,
            "currency": info.currency,
            "leverage": info.leverage,
            "balance": float(info.balance),
            "equity": float(info.equity),
            "margin": float(info.margin),
            "margin_free": float(info.margin_free),
            "margin_level": float(info.margin_level) if info.margin_level else 0.0,
            "profit": float(info.profit),
        }
    except Mt5UnavailableError:
        raise
    except Exception as e:
        raise Mt5UnavailableError(f"Account info error: {e}") from e


def shutdown_mt5() -> None:
    """Shutdown MT5 connection."""
    mt5 = _get_mt5()
    try:
        mt5.shutdown()
    except Exception:
        pass  # ponytail: best-effort shutdown, swallow errors


# === SAFETY ASSERTION ===
# This module must NEVER contain order_send, order_modify, or order_close.
def _verify_readonly():
    """Module-level check: these functions must not exist here."""
    import sys
    mod = sys.modules[__name__]
    forbidden = ["order_send", "order_modify", "order_close"]
    for fn in forbidden:
        assert not hasattr(mod, fn), f"FORBIDDEN: {fn} must not exist in mt5_gateway"


_verify_readonly()
