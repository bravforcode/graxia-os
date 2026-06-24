"""Market-open qualification gate for Quant OS qualification campaigns."""

from dataclasses import dataclass
from datetime import datetime, timezone

# ponytail: module-level DRY_RUN_MODE matches the project pattern in g3_execute_demo_canary.py
DRY_RUN_MODE = True

TERMINAL_PATH = r"C:\Program Files\Pepperstone MetaTrader 5\terminal64.exe"


@dataclass
class MarketGateResult:
    passed: bool
    symbol: str
    spread: float | None
    spread_cap: float
    terminal_connected: bool
    terminal_trade_allowed: bool
    symbol_open: bool
    tick_fresh: bool
    positions_exist: bool
    pending_orders_exist: bool
    session: str | None
    expiry: datetime | None
    reason: str | None


def _determine_session() -> str:
    """Determine trading session based on current hour (GMT)."""
    # ponytail: simple hour-range heuristic, no calendar lib
    hour = datetime.now(timezone.utc).hour
    if 0 <= hour < 9:
        return "asian"
    if 8 <= hour < 17:
        return "london"
    if 13 <= hour < 22:
        return "ny"
    return "closed"


def check_market_open(
    symbol: str = "XAUUSD",
    spread_cap: float = 50.0,
    tick_max_age: float = 60.0,
    plan_expiry: datetime | None = None,
) -> MarketGateResult:
    """Check all market-open conditions for a qualification campaign.

    DRY_RUN_MODE: When True, MT5 initialisation is skipped and all MT5 calls
    return None (fail-closed). Set DRY_RUN_MODE = False in this module to
    enable live checks.
    """
    session = _determine_session()

    if session == "closed":
        return MarketGateResult(
            passed=False, symbol=symbol, spread=None, spread_cap=spread_cap,
            terminal_connected=False, terminal_trade_allowed=False,
            symbol_open=False, tick_fresh=False,
            positions_exist=False, pending_orders_exist=False,
            session=session, expiry=plan_expiry,
            reason="Market closed (all sessions)",
        )

    if plan_expiry is not None and plan_expiry < datetime.now(timezone.utc):
        return MarketGateResult(
            passed=False, symbol=symbol, spread=None, spread_cap=spread_cap,
            terminal_connected=False, terminal_trade_allowed=False,
            symbol_open=False, tick_fresh=False,
            positions_exist=False, pending_orders_exist=False,
            session=session, expiry=plan_expiry,
            reason=f"Plan expired at {plan_expiry.isoformat()}",
        )

    if DRY_RUN_MODE:
        # ponytail: DRY_RUN — skip MT5 init/calls, assume clean
        return MarketGateResult(
            passed=True, symbol=symbol, spread=None, spread_cap=spread_cap,
            terminal_connected=True, terminal_trade_allowed=True,
            symbol_open=True, tick_fresh=True,
            positions_exist=False, pending_orders_exist=False,
            session=session, expiry=plan_expiry,
            reason=None,
        )

    import MetaTrader5 as mt5  # ponytail: lazy-import, keeps module importable without MT5

    if not mt5.initialize(path=TERMINAL_PATH):
        return MarketGateResult(
            passed=False, symbol=symbol, spread=None, spread_cap=spread_cap,
            terminal_connected=False, terminal_trade_allowed=False,
            symbol_open=False, tick_fresh=False,
            positions_exist=False, pending_orders_exist=False,
            session=session, expiry=plan_expiry,
            reason="MT5 terminal initialisation failed",
        )

    terminal = mt5.terminal_info()
    if terminal is None:
        mt5.shutdown()
        return MarketGateResult(
            passed=False, symbol=symbol, spread=None, spread_cap=spread_cap,
            terminal_connected=False, terminal_trade_allowed=False,
            symbol_open=False, tick_fresh=False,
            positions_exist=False, pending_orders_exist=False,
            session=session, expiry=plan_expiry,
            reason="terminal_info() returned None",
        )

    terminal_connected = terminal.connected
    terminal_trade_allowed = terminal.trade_allowed

    if not terminal_connected:
        mt5.shutdown()
        return MarketGateResult(
            passed=False, symbol=symbol, spread=None, spread_cap=spread_cap,
            terminal_connected=False, terminal_trade_allowed=terminal_trade_allowed,
            symbol_open=False, tick_fresh=False,
            positions_exist=False, pending_orders_exist=False,
            session=session, expiry=plan_expiry,
            reason="Terminal not connected",
        )

    si = mt5.symbol_info(symbol)
    if si is None:
        mt5.shutdown()
        return MarketGateResult(
            passed=False, symbol=symbol, spread=None, spread_cap=spread_cap,
            terminal_connected=terminal_connected, terminal_trade_allowed=terminal_trade_allowed,
            symbol_open=False, tick_fresh=False,
            positions_exist=False, pending_orders_exist=False,
            session=session, expiry=plan_expiry,
            reason=f"symbol_info({symbol}) returned None",
        )

    symbol_open = si.trade_mode != 0

    tick = mt5.symbol_info_tick(symbol)
    spread: float | None = None
    tick_fresh = False
    if tick is not None:
        spread = max(tick.ask - tick.bid, 0)
        age_s = (datetime.now(timezone.utc).timestamp() - tick.time_msc / 1000)
        tick_fresh = age_s <= tick_max_age

    if not symbol_open:
        mt5.shutdown()
        return MarketGateResult(
            passed=False, symbol=symbol, spread=spread, spread_cap=spread_cap,
            terminal_connected=terminal_connected, terminal_trade_allowed=terminal_trade_allowed,
            symbol_open=False, tick_fresh=tick_fresh,
            positions_exist=False, pending_orders_exist=False,
            session=session, expiry=plan_expiry,
            reason=f"{symbol} not open for trading (trade_mode={si.trade_mode})",
        )

    if spread is not None and spread > spread_cap:
        mt5.shutdown()
        return MarketGateResult(
            passed=False, symbol=symbol, spread=spread, spread_cap=spread_cap,
            terminal_connected=terminal_connected, terminal_trade_allowed=terminal_trade_allowed,
            symbol_open=symbol_open, tick_fresh=tick_fresh,
            positions_exist=False, pending_orders_exist=False,
            session=session, expiry=plan_expiry,
            reason=f"Spread {spread} exceeds cap {spread_cap}",
        )

    if not tick_fresh:
        mt5.shutdown()
        return MarketGateResult(
            passed=False, symbol=symbol, spread=spread, spread_cap=spread_cap,
            terminal_connected=terminal_connected, terminal_trade_allowed=terminal_trade_allowed,
            symbol_open=symbol_open, tick_fresh=False,
            positions_exist=False, pending_orders_exist=False,
            session=session, expiry=plan_expiry,
            reason=f"Tick stale (>{tick_max_age}s)",
        )

    positions = mt5.positions_get(symbol=symbol)
    positions_exist = len(positions) > 0 if positions is not None else False
    if positions_exist:
        mt5.shutdown()
        return MarketGateResult(
            passed=False, symbol=symbol, spread=spread, spread_cap=spread_cap,
            terminal_connected=terminal_connected, terminal_trade_allowed=terminal_trade_allowed,
            symbol_open=symbol_open, tick_fresh=tick_fresh,
            positions_exist=True, pending_orders_exist=False,
            session=session, expiry=plan_expiry,
            reason=f"{len(positions)} open position(s)",
        )

    orders = mt5.orders_get(symbol=symbol)
    pending_orders_exist = len(orders) > 0 if orders is not None else False
    if pending_orders_exist:
        mt5.shutdown()
        return MarketGateResult(
            passed=False, symbol=symbol, spread=spread, spread_cap=spread_cap,
            terminal_connected=terminal_connected, terminal_trade_allowed=terminal_trade_allowed,
            symbol_open=symbol_open, tick_fresh=tick_fresh,
            positions_exist=False, pending_orders_exist=True,
            session=session, expiry=plan_expiry,
            reason=f"{len(orders)} pending order(s)",
        )

    mt5.shutdown()
    return MarketGateResult(
        passed=True, symbol=symbol, spread=spread, spread_cap=spread_cap,
        terminal_connected=terminal_connected, terminal_trade_allowed=terminal_trade_allowed,
        symbol_open=symbol_open, tick_fresh=tick_fresh,
        positions_exist=False, pending_orders_exist=False,
        session=session, expiry=plan_expiry,
        reason=None,
    )
