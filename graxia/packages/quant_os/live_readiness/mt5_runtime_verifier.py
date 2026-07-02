"""MT5 Runtime Verifier — read-only verification of MT5 capabilities.

Runs the full verification sequence from the master plan:
  initialize → terminal_info → account_info (redacted) → expected server/profile check
  → terminal connected check → symbol_select → symbol_info → symbol_info_tick
  → copy_ticks_range test → order_calc_profit test → order_calc_margin test
  → order_check test only → positions_get → orders_get → history_orders_get
  → history_deals_get → UTC/time sanity check → persist smoke report

CRITICAL CONSTRAINT: This module is READ-ONLY. No order submission.
"""

from __future__ import annotations

import datetime as _dt
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .broker_profile import BrokerProfile

from broker.mt5_gateway import Mt5UnavailableError, _get_mt5

from .runtime_capabilities import RuntimeCapabilities


def _mask_account(login: int) -> str:
    s = str(login)
    if len(s) <= 4:
        return "****"
    return s[:2] + "*" * (len(s) - 4) + s[-2:]


def _mask_server(server: str) -> str:
    parts = server.split("-")
    if len(parts) >= 2:
        return parts[0] + "-" + "*" * len(parts[1])
    return server


def verify_mt5_runtime(
    profile: BrokerProfile,
    mt5_path: str = "",
    timeout_ms: int = 10000,
) -> RuntimeCapabilities:
    """Run the full MT5 verification sequence. Returns RuntimeCapabilities."""
    caps = RuntimeCapabilities()
    mt5 = None

    def _record(issue: str) -> None:
        caps.issues.append(issue)

    # ── Step 1: Initialize ──────────────────────────────────────────────
    try:
        mt5 = _get_mt5()
        init_kwargs: dict = {}
        if mt5_path:
            init_kwargs["path"] = mt5_path
        init_kwargs["timeout"] = timeout_ms
        if not mt5.initialize(**init_kwargs):
            _record(f"mt5.initialize failed: {mt5.last_error()}")
            return caps
        caps.mt5_initialized = True
    except Mt5UnavailableError as e:
        _record(f"MT5 unavailable: {e}")
        return caps
    except Exception as e:
        _record(f"mt5.initialize exception: {e}")
        return caps

    # ── Step 2: Terminal info ───────────────────────────────────────────
    try:
        ti = mt5.terminal_info()
        if ti is None:
            _record("terminal_info() returned None")
        else:
            caps.terminal_info = {
                "build": getattr(ti, "build", 0),
                "connected": getattr(ti, "connected", False),
                "trade_allowed": getattr(ti, "trade_allowed", False),
                "max_bars": getattr(ti, "max_bars", 0),
                "name": getattr(ti, "name", ""),
                "path": getattr(ti, "path", ""),
            }
            caps.terminal_connected = bool(getattr(ti, "connected", False))
    except Exception as e:
        _record(f"terminal_info error: {e}")

    # ── Step 3: Account info (REDACTED) ────────────────────────────────
    try:
        ai = mt5.account_info()
        if ai is None:
            _record("account_info() returned None")
        else:
            caps.account_info_redacted = {
                "login_masked": _mask_account(getattr(ai, "login", 0)),
                "server_masked": _mask_server(getattr(ai, "server", "")),
                "currency": getattr(ai, "currency", ""),
                "leverage": getattr(ai, "leverage", 0),
                "balance": float(getattr(ai, "balance", 0.0)),
                "equity": float(getattr(ai, "equity", 0.0)),
                "margin": float(getattr(ai, "margin", 0.0)),
                "margin_free": float(getattr(ai, "margin_free", 0.0)),
                "margin_level": float(getattr(ai, "margin_level", 0.0)),
                "profit": float(getattr(ai, "profit", 0.0)),
            }
            caps.server_name = getattr(ai, "server", "")
            caps.account_currency = getattr(ai, "currency", "")
    except Exception as e:
        _record(f"account_info error: {e}")

    # ── Step 4: Expected server / profile check ─────────────────────────
    if caps.server_name and caps.server_name != profile.expected_server:
        _record(f"server mismatch: expected '{profile.expected_server}', " f"got '{_mask_server(caps.server_name)}'")
    if caps.account_currency and caps.account_currency != profile.account_currency:
        _record(f"currency mismatch: expected '{profile.account_currency}', " f"got '{caps.account_currency}'")

    # ── Step 5: Terminal connected check ────────────────────────────────
    if not caps.terminal_connected:
        _record("terminal reports disconnected")

    # ── Steps 6-8: Symbol probe (first canonical symbol) ────────────────
    probe_symbol = next(iter(profile.symbols), None) if profile.symbols else None
    if probe_symbol is None:
        _record("no symbols defined in profile")

    if probe_symbol and caps.mt5_initialized and caps.terminal_connected:
        broker_symbol = profile.symbols.get(probe_symbol, probe_symbol)

        # Step 6: symbol_select
        try:
            if not mt5.symbol_select(broker_symbol, True):
                _record(f"symbol_select('{broker_symbol}') failed")
            else:
                caps.symbols_available.append(broker_symbol)
        except Exception as e:
            _record(f"symbol_select error: {e}")

        # Step 7: symbol_info
        try:
            si = mt5.symbol_info(broker_symbol)
            if si is None:
                _record(f"symbol_info('{broker_symbol}') returned None")
        except Exception as e:
            _record(f"symbol_info error: {e}")

        # Step 8: symbol_info_tick
        try:
            tick = mt5.symbol_info_tick(broker_symbol)
            if tick is None:
                _record(f"symbol_info_tick('{broker_symbol}') returned None")
            else:
                caps.tick_access = True
        except Exception as e:
            _record(f"symbol_info_tick error: {e}")

        # ── Step 9: copy_ticks_range test ───────────────────────────────
        try:
            now = mt5.symbol_info_tick(broker_symbol)
            if now is not None:
                t = now.time
                ticks = mt5.copy_ticks_range(t - 10, t, mt5.COPY_TICKS_ALL)
                if ticks is not None and len(ticks) > 0:
                    caps.bar_access = True
                else:
                    _record(f"copy_ticks_range returned empty for {broker_symbol}")
        except Exception as e:
            _record(f"copy_ticks_range error: {e}")

        # ── Step 10: order_calc_profit test ─────────────────────────────
        try:
            result = mt5.order_calc_profit(mt5.ORDER_TYPE_BUY, broker_symbol, 0.01, 1.0, 1.001)
            caps.order_calc_profit = result is not None
        except Exception as e:
            _record(f"order_calc_profit error: {e}")

        # ── Step 11: order_calc_margin test ─────────────────────────────
        try:
            result = mt5.order_calc_margin(mt5.ORDER_TYPE_BUY, broker_symbol, 0.01, 1.0)
            caps.order_calc_margin = result is not None
        except Exception as e:
            _record(f"order_calc_margin error: {e}")

        # ── Step 12: order_check test only (READ-ONLY) ──────────────────
        try:
            # Minimal synthetic request — never submitted, just validated
            test_request = {
                "action": 5,  # mt5.TRADE_ACTION_DEAL (constant)
                "symbol": broker_symbol,
                "volume": 0.01,
                "type": mt5.ORDER_TYPE_BUY,
                "price": 1.0,
                "deviation": 20,
                "magic": 0,
                "comment": "READONLY_TEST",
                "type_time": mt5.ORDER_TIME_GTC,
                "type_filling": mt5.ORDER_FILLING_IOC,
            }
            result = mt5.order_check(test_request)
            # We expect retcode != 0 (e.g. bad price), but the call succeeded
            if result is None:
                _record("order_check returned None")
        except Exception as e:
            _record(f"order_check error: {e}")

    # ── Step 13: positions_get ──────────────────────────────────────────
    try:
        positions = mt5.positions_get()
        caps.positions_visible = positions is not None
        if positions is None:
            _record("positions_get returned None")
    except Exception as e:
        _record(f"positions_get error: {e}")

    # ── Step 14: orders_get ─────────────────────────────────────────────
    try:
        orders = mt5.orders_get()
        caps.orders_visible = orders is not None
        if orders is None:
            _record("orders_get returned None")
    except Exception as e:
        _record(f"orders_get error: {e}")

    # ── Step 15: history_orders_get ─────────────────────────────────────
    try:
        now = _dt.datetime.utcnow()
        week_ago = now - _dt.timedelta(days=7)
        history = mt5.history_orders_get(week_ago, now)
        caps.history_visible = history is not None
        if history is None:
            _record("history_orders_get returned None")
    except Exception as e:
        _record(f"history_orders_get error: {e}")

    # ── Step 16: history_deals_get ──────────────────────────────────────
    try:
        now = _dt.datetime.utcnow()
        week_ago = now - _dt.timedelta(days=7)
        deals = mt5.history_deals_get(week_ago, now)
        if deals is None:
            _record("history_deals_get returned None")
    except Exception as e:
        _record(f"history_deals_get error: {e}")

    # ── Step 17: UTC / time sanity check ────────────────────────────────
    try:
        server_time = mt5.symbol_info_tick(probe_symbol or "EURUSD")
        if server_time is not None:
            server_ts = _dt.datetime.utcfromtimestamp(server_time.time)
            local_ts = _dt.datetime.utcnow()
            diff_ms = int(abs((server_ts - local_ts).total_seconds() * 1000))
            caps.utc_offset_ms = diff_ms
            if diff_ms > 5000:
                _record(f"server time offset {diff_ms}ms exceeds 5s threshold")
    except Exception as e:
        _record(f"time sanity check error: {e}")

    return caps
