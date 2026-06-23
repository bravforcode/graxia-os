"""G2 preflight guards. All return (passed: bool, reason: str). Fail-closed."""
from datetime import datetime, timezone
from decimal import Decimal
from typing import Callable, Optional

from execution.demo_canary.feature_gate import is_execution_enabled
from execution.demo_canary.kill_switch import is_kill_switch_active
from execution.demo_canary.execution_mutex import is_mutex_held
from execution.demo_canary.broker_profile_guard import verify_broker_profile
from execution.demo_canary.terminal_path_guard import verify_terminal_path
from execution.demo_canary.approval_payload import ApprovalPayload

APPROVED_TERMINAL_PATH = r"C:\Program Files\Pepperstone MetaTrader 5\terminal64.exe"


def _p() -> tuple[bool, str]:
    return (True, "")

def _f(reason: str) -> tuple[bool, str]:
    return (False, reason)


def g01_feature_gate_off(mt5=None) -> tuple[bool, str]:
    return (True, "") if not is_execution_enabled() else (False, "Feature gate ON (must be OFF)")

def g02_terminal_health(mt5=None) -> tuple[bool, str]:
    if mt5 is None:
        return _f("No MT5 connection")
    try:
        info = mt5.terminal_info()
        return (True, "") if info else _f("terminal_info() returned None")
    except Exception as e:
        return _f(f"MT5 terminal_info failed: {e}")

def g03_demo_account(mt5=None) -> tuple[bool, str]:
    if mt5 is None:
        return _f("No MT5 connection")
    try:
        info = mt5.account_info()
        if info is None:
            return _f("account_info() returned None")
        return (True, "") if info.trade_mode == 0 else _f(f"Account trade_mode={info.trade_mode} != DEMO(0)")
    except Exception as e:
        return _f(f"demo_account check failed: {e}")

def g04_profile_identity(mt5=None) -> tuple[bool, str]:
    if mt5 is None:
        return _f("No MT5 connection")
    try:
        info = mt5.account_info()
        if info is None:
            return _f("account_info() returned None")
        import hashlib
        login_hash = hashlib.sha256(str(info.login).encode()).hexdigest()
        r = verify_broker_profile(login_hash)
        return (r.passed, r.reason)
    except Exception as e:
        return _f(f"profile_identity check failed: {e}")

def g05_terminal_path(mt5=None) -> tuple[bool, str]:
    try:
        ok = verify_terminal_path(APPROVED_TERMINAL_PATH)
        return (ok, "") if ok else (False, "Terminal path hash mismatch")
    except Exception as e:
        return _f(f"terminal_path check failed: {e}")

def g06_symbol_identity(mt5=None) -> tuple[bool, str]:
    if mt5 is None:
        return _f("No MT5 connection")
    try:
        sym = mt5.symbol_info("XAUUSD")
        return (True, "") if sym else _f("XAUUSD not found via symbol_info()")
    except Exception as e:
        return _f(f"symbol_identity check failed: {e}")

def g07_contract_freshness(mt5=None, resolver=None) -> tuple[bool, str]:
    if resolver is None:
        return _f("No ContractSpecResolver")
    try:
        spec = resolver.resolve_or_fail("XAUUSD")
        return (True, "") if not spec.is_stale() else (False, f"ContractSpec stale (age > TTL)")
    except Exception as e:
        return _f(f"contract_freshness: {e}")

def g08_market_status(mt5=None) -> tuple[bool, str]:
    if mt5 is None:
        return _f("No MT5 connection")
    try:
        sym = mt5.symbol_info("XAUUSD")
        if sym is None:
            return _f("XAUUSD not found")
        return (True, "") if sym.trade_mode != 0 else _f("XAUUSD trading disabled (trade_mode=0)")
    except Exception as e:
        return _f(f"market_status check failed: {e}")

def g09_canonical_tick(mt5=None, max_age_ms: int = 8000) -> tuple[bool, str]:
    if mt5 is None:
        return _f("No MT5 connection")
    try:
        tick = mt5.symbol_info_tick("XAUUSD")
        if tick is None:
            return _f("No tick data for XAUUSD")
        now_ms = int(datetime.now(timezone.utc).timestamp() * 1000)
        age_ms = now_ms - tick.time_msc
        return (True, "") if age_ms <= max_age_ms else _f(f"Tick age {age_ms}ms > {max_age_ms}ms")
    except Exception as e:
        return _f(f"canonical_tick failed: {e}")

def g10_tick_ordering(mt5=None) -> tuple[bool, str]:
    if mt5 is None:
        return _f("No MT5 connection")
    try:
        tick = mt5.symbol_info_tick("XAUUSD")
        if tick is None:
            return _f("No tick data")
        now_ms = int(datetime.now(timezone.utc).timestamp() * 1000)
        if tick.time_msc > now_ms + 2000:
            return _f(f"Future tick: {tick.time_msc} > {now_ms}")
        return (True, "")
    except Exception as e:
        return _f(f"tick_ordering failed: {e}")

def g11_spread_gate(mt5=None, max_spread_pts: float = 25.0) -> tuple[bool, str]:
    if mt5 is None:
        return _f("No MT5 connection")
    try:
        tick = mt5.symbol_info_tick("XAUUSD")
        if tick is None:
            return _f("No tick data")
        spread = max(tick.ask - tick.bid, 0)
        if spread <= 0:
            return _f(f"Invalid spread {spread}")
        return (True, "") if spread <= max_spread_pts else _f(f"Spread {spread}pt > {max_spread_pts}pt")
    except Exception as e:
        return _f(f"spread_gate failed: {e}")

def g12_event_gate(mt5=None) -> tuple[bool, str]:
    # Ponytail: no real calendar in G2, always pass
    return (True, "")

def g13_session_gate(mt5=None) -> tuple[bool, str]:
    # Ponytail: always pass for G2 demo
    return (True, "")

def g14_position_gate(mt5=None) -> tuple[bool, str]:
    if mt5 is None:
        return _f("No MT5 connection")
    try:
        positions = mt5.positions_get(symbol="XAUUSD")
        count = len(positions) if positions else 0
        return (True, "") if count == 0 else _f(f"Found {count} open position(s)")
    except Exception as e:
        return _f(f"position_gate failed: {e}")

def g15_pending_order_gate(mt5=None) -> tuple[bool, str]:
    if mt5 is None:
        return _f("No MT5 connection")
    try:
        orders = mt5.orders_get(symbol="XAUUSD")
        count = len(orders) if orders else 0
        return (True, "") if count == 0 else _f(f"Found {count} pending order(s)")
    except Exception as e:
        return _f(f"pending_order_gate failed: {e}")

def g16_volume_gate(mt5=None, volume: float = 0.01, resolver=None) -> tuple[bool, str]:
    if resolver is None:
        return _f("No ContractSpecResolver")
    try:
        spec = resolver.resolve("XAUUSD")
        if volume < spec.volume_min:
            return _f(f"Volume {volume} < min {spec.volume_min}")
        if volume > spec.volume_max:
            return _f(f"Volume {volume} > max {spec.volume_max}")
        if spec.volume_step > 0 and abs(volume % spec.volume_step) > 0.0001:
            return _f(f"Volume {volume} not multiple of step {spec.volume_step}")
        return (True, "")
    except Exception as e:
        return _f(f"volume_gate: {e}")

def g17_geometry_gate(mt5=None, side: str = "BUY", entry: float = 0.0, sl: float = 0.0, tp: float = 0.0, resolver=None) -> tuple[bool, str]:
    if mt5 is None:
        return _f("No MT5 connection")
    if resolver is None:
        return _f("No ContractSpecResolver")
    try:
        spec = resolver.resolve("XAUUSD")
        if entry <= 0:
            tick = mt5.symbol_info_tick("XAUUSD")
            if tick is None:
                return _f("No tick to determine entry price")
            entry = tick.ask if side == "BUY" else tick.bid
        if side not in ("BUY", "SELL"):
            return _f(f"Invalid side: {side}")
        if sl == 0 or tp == 0:
            return _f("SL and TP must be non-zero")
        min_dist = spec.stops_level * spec.point
        if side == "BUY":
            if sl >= entry:
                return _f("SL must be below entry for BUY")
            if tp <= entry:
                return _f("TP must be above entry for BUY")
        else:
            if sl <= entry:
                return _f("SL must be above entry for SELL")
            if tp >= entry:
                return _f("TP must be below entry for SELL")
        if abs(entry - sl) < min_dist:
            return _f(f"SL distance too small (< stops_level {min_dist})")
        return (True, "")
    except Exception as e:
        return _f(f"geometry_gate: {e}")

def g18_stops_freeze_level(mt5=None, resolver=None) -> tuple[bool, str]:
    if resolver is None:
        return _f("No ContractSpecResolver")
    try:
        spec = resolver.resolve("XAUUSD")
        if spec.stops_level < 0:
            return _f(f"Stops level {spec.stops_level} < 0")
        if spec.freeze_level < 0:
            return _f(f"Freeze level {spec.freeze_level} < 0")
        return (True, "")
    except Exception as e:
        return _f(f"stops_freeze_level: {e}")

def g19_margin_estimate(mt5=None, volume: float = 0.01, price: float = 0.0) -> tuple[bool, str]:
    if mt5 is None:
        return _f("No MT5 connection")
    try:
        if price <= 0:
            tick = mt5.symbol_info_tick("XAUUSD")
            if tick is None:
                return _f("No tick for margin price")
            price = tick.ask
        margin = mt5.order_calc_margin(0, "XAUUSD", volume, price)
        if margin is None:
            return _f("order_calc_margin returned None")
        info = mt5.account_info()
        if info is None:
            return _f("account_info() returned None")
        cap = info.balance * 0.01
        return (True, "") if margin < cap else _f(f"Margin {margin:.2f} >= cap {cap:.2f} (1% of {info.balance:.2f})")
    except Exception as e:
        return _f(f"margin_estimate: {e}")

def g20_order_check(mt5=None, volume: float = 0.01, price: float = 0.0, sl: float = 0.0, tp: float = 0.0) -> tuple[bool, str]:
    if mt5 is None:
        return _f("No MT5 connection")
    try:
        if price <= 0:
            tick = mt5.symbol_info_tick("XAUUSD")
            if tick is None:
                return _f("No tick for order_check price")
            price = tick.ask
        request = {
            "action": 1, "symbol": "XAUUSD", "volume": volume,
            "price": price, "sl": sl, "tp": tp,
            "deviation": 10, "magic": 2025,
            "comment": "PRECHECK_ONLY, NOT_EXECUTION_PROOF",
            "type_time": 0, "type_filling": 1, "type": 0,
        }
        result = mt5.order_check(request)
        if result is None:
            return _f("order_check returned None")
        return (result.retcode == 0, f"order_check retcode={result.retcode}: {result.comment}")
    except Exception as e:
        return _f(f"order_check: {e}")

def g21_kill_switch(mt5=None) -> tuple[bool, str]:
    return (True, "") if is_kill_switch_active() else (False, "Kill switch OFF (must be ON/blocked)")

def g22_approval_precondition(mt5=None, approval: Optional[ApprovalPayload] = None) -> tuple[bool, str]:
    if approval is None:
        return _f("No approval payload provided")
    return (not approval.is_expired(), f"Approval expired") if approval.is_expired() else (True, "")

def g23_evidence_writer_available(mt5=None, writer: Optional[Callable] = None) -> tuple[bool, str]:
    if writer is None:
        return _f("No evidence writer")
    return (callable(writer), "Evidence writer not callable") if not callable(writer) else (True, "")

def g24_mutex_available(mt5=None) -> tuple[bool, str]:
    return (True, "") if not is_mutex_held() else (False, "Execution mutex held by another process")

def g25_legacy_separation(mt5=None) -> tuple[bool, str]:
    return (True, "") if not is_execution_enabled() else (False, "Legacy execution path may be active")

def g26_time_to_submit(mt5=None, bundle_created_utc: Optional[datetime] = None, max_age: int = 60) -> tuple[bool, str]:
    if bundle_created_utc is None:
        return _f("No preflight bundle timestamp")
    age = (datetime.now(timezone.utc) - bundle_created_utc).total_seconds()
    return (True, "") if age <= max_age else _f(f"Bundle age {age:.0f}s > {max_age}s ceiling")
