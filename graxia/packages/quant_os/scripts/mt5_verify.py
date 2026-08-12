#!/usr/bin/env python3
"""
MT5 Setup Verification - XAUUSD Paper Trading Preflight
========================================================
Connects to Pepperstone MT5, inspects XAUUSD symbol properties,
account type, leverage, spread, stops level, and produces a
PASS/FAIL checklist for paper-trading readiness.

Usage:
    python scripts/mt5_verify.py
    python scripts/mt5_verify.py --lot-size 0.1
"""

import argparse
import sys
from datetime import datetime, UTC

import MetaTrader5 as mt5

TERMINAL_PATH = r"C:\Program Files\Pepperstone MetaTrader 5\terminal64.exe"
TIMEOUT_MS = 30_000
SYMBOL = "XAUUSD"
CONTRACT_SIZE = 100
MIN_STOP_DOLLARS = 0.50

EXECUTION_LABELS = {
    0: "REQUEST",
    1: "INSTANT",
    2: "MARKET",
    3: "EXCHANGE",
}


def _check(condition: bool, label: str, detail: str = "") -> str:
    status = "PASS" if condition else "FAIL"
    icon = "[PASS]" if condition else "[FAIL]"
    pad = f"  --  {detail}" if detail else ""
    return f"  {icon} {label}{pad}"


def _info(label: str, value: object) -> str:
    return f"  [INFO] {label}: {value}"


def fmt_dollars(val: float) -> str:
    return f"${val:,.2f}"


def main() -> None:
    parser = argparse.ArgumentParser(description="MT5 XAUUSD setup verification")
    parser.add_argument(
        "--lot-size",
        type=float,
        default=0.1,
        help="Lot size to validate stop-distance against (default: 0.1)",
    )
    args = parser.parse_args()
    lot_size = args.lot_size
    ts = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")

    print("=" * 62)
    print("  MT5 SETUP VERIFICATION  --  XAUUSD Paper Trading Preflight")
    print(f"  Run at {ts}")
    print("=" * 62)

    checks: list[tuple[bool, str, str]] = []
    infos: list[str] = []
    verdict = True

    # 1. Initialise MT5
    init_ok = mt5.initialize(path=TERMINAL_PATH, timeout=TIMEOUT_MS)
    if not init_ok:
        err = mt5.last_error()
        print(_check(False, "MT5 initialised", f"error: {err}"))
        print(_check(False, "OVERALL VERDICT", "Cannot continue without MT5 connection"))
        mt5.shutdown()
        sys.exit(1)
    print(_check(True, "MT5 initialised", f"terminal: {TERMINAL_PATH}"))

    # 2. Account info
    account = mt5.account_info()
    if account is None:
        print(_check(False, "Account info readable", "mt5.account_info() returned None"))
        mt5.shutdown()
        sys.exit(1)

    server_lower = (account.server or "").lower()
    is_demo = "demo" in server_lower or "contest" in server_lower
    account_type = "DEMO" if is_demo else "REAL (or unknown)"
    infos.append(_info("Account type", account_type))
    infos.append(_info("Server", account.server))
    infos.append(_info("Login", account.login))
    infos.append(_info("Balance", fmt_dollars(account.balance)))
    infos.append(_info("Equity", fmt_dollars(account.equity)))
    infos.append(_info("Leverage", f"1:{account.leverage}"))
    infos.append(_info("Currency", account.currency))
    infos.append(_info("Trade allowed", account.trade_allowed))

    checks.append((
        is_demo,
        "Account is a demo / paper account",
        f"server={account.server!r}",
    ))

    # 3. Symbol visibility
    symbols = mt5.symbols_get()
    symbol_names = [s.name for s in symbols] if symbols else []
    xau_found = SYMBOL in symbol_names

    checks.append((
        xau_found,
        f"{SYMBOL} found in symbol list",
        f"{len(symbol_names)} symbols total",
    ))

    if not xau_found:
        print(_check(False, f"{SYMBOL} NOT in symbol list -- cannot continue"))
        gold_like = [s for s in symbol_names if "XAU" in s or "GOLD" in s]
        if gold_like:
            print(_info("Gold-like symbols found", ", ".join(gold_like)))
        mt5.shutdown()
        sys.exit(1)

    # 4. Symbol select & tick
    select_ok = mt5.symbol_select(SYMBOL, True)
    checks.append((
        select_ok,
        f"{SYMBOL} selected in Market Watch",
        "",
    ))

    tick = mt5.symbol_info_tick(SYMBOL)
    tick_ok = tick is not None and tick.bid > 0 and tick.ask > 0
    checks.append((
        tick_ok,
        f"{SYMBOL} tick data available",
        f"bid={tick.bid}  ask={tick.ask}" if tick_ok else "no tick",
    ))

    sym = mt5.symbol_info(SYMBOL)
    sym_ok = sym is not None
    checks.append((
        sym_ok,
        f"{SYMBOL} symbol_info readable",
        "",
    ))

    if not (tick_ok and sym_ok):
        print(_check(False, "OVERALL VERDICT", "Symbol info unavailable"))
        mt5.shutdown()
        sys.exit(1)

    # 5. Spread
    spread_points = round((tick.ask - tick.bid) / sym.point) if sym.point > 0 else 0
    spread_dollars = round(tick.ask - tick.bid, 2)
    spread_ok = spread_points <= 100
    checks.append((
        spread_ok,
        "Spread within acceptable range",
        f"{spread_points} pts (${spread_dollars:.2f})",
    ))

    # 6. Trade execution mode
    exec_mode = getattr(sym, "trade_execution", None)
    exec_label = EXECUTION_LABELS.get(exec_mode, f"UNKNOWN ({exec_mode})")
    infos.append(_info("Trade execution mode", exec_label))
    if exec_mode != 2:
        infos.append(_info(
            "  ! execution mode note",
            "Non-MARKET execution may cause requotes. Verify broker config.",
        ))

    # 7. Stops level / freeze level
    stops_level_pts = getattr(sym, "trade_stops_level", None)
    freeze_level_pts = getattr(sym, "trade_freeze_level", None)
    infos.append(_info("Stops level (points)", stops_level_pts))
    infos.append(_info("Freeze level (points)", freeze_level_pts))

    if stops_level_pts is not None and sym.point > 0:
        min_stop_price = stops_level_pts * sym.point
        min_stop_dollars = min_stop_price * CONTRACT_SIZE * lot_size
    else:
        min_stop_price = 0.0
        min_stop_dollars = 0.0

    infos.append(_info(
        "Min stop distance (price)",
        fmt_dollars(min_stop_price),
    ))
    infos.append(_info(
        f"Min stop distance for {lot_size} lot",
        fmt_dollars(min_stop_dollars),
    ))

    # 8. Verify min stop >= $0.50 (or 0 = no restriction)
    if stops_level_pts == 0:
        stop_ok = True
        stop_detail = "stops_level=0 (no minimum) — B2 $6.30 OK"
    else:
        stop_ok = min_stop_dollars >= MIN_STOP_DOLLARS
        stop_detail = f"actual={fmt_dollars(min_stop_dollars)}"
    checks.append((
        stop_ok,
        f"Min stop distance >= {fmt_dollars(MIN_STOP_DOLLARS)} for {lot_size} lot",
        stop_detail,
    ))

    # 9. Volume step sanity
    infos.append(_info("Volume min", getattr(sym, "volume_min", None)))
    infos.append(_info("Volume max", getattr(sym, "volume_max", None)))
    infos.append(_info("Volume step", getattr(sym, "volume_step", None)))

    # 10. Order check (read-only preflight) — try IOC then FOK
    if tick_ok and sym_ok:
        entry = tick.ask
        sl_dist = max(stops_level_pts or 10, 10) * sym.point
        check_ok = False
        check_detail = "order_check not attempted"
        for fill_type, fill_label in [(mt5.ORDER_FILLING_IOC, "IOC"), (mt5.ORDER_FILLING_FOK, "FOK")]:
            request = {
                "action": mt5.TRADE_ACTION_DEAL,
                "symbol": SYMBOL,
                "volume": lot_size,
                "type": mt5.ORDER_TYPE_BUY,
                "price": entry,
                "sl": entry - sl_dist,
                "tp": entry + sl_dist,
                "deviation": 10,
                "magic": 999999,
                "comment": "MT5_VERIFY_DRY_RUN",
                "type_time": mt5.ORDER_TIME_GTC,
                "type_filling": fill_type,
            }
            check = mt5.order_check(request)
            if check is not None and check.retcode == 0:
                check_ok = True
                check_detail = f"OK ({fill_label})"
                break
            check_detail = f"retcode={check.retcode} ({fill_label})"
        checks.append((
            check_ok,
            "Order check (read-only preflight) passed",
            check_detail,
        ))
    else:
        checks.append((False, "Order check (read-only preflight) skipped", "no tick/sym"))

    # Print checklist
    print()
    print("-- ACCOUNT ------------------------------------------------------")
    for line in infos:
        print(line)

    print()
    print("-- CHECKS -------------------------------------------------------")
    for ok, label, detail in checks:
        print(_check(ok, label, detail))
        if not ok:
            verdict = False

    print()
    print("-- SUMMARY ------------------------------------------------------")
    passed = sum(1 for ok, _, _ in checks if ok)
    failed = sum(1 for ok, _, _ in checks if not ok)
    outcome = "PASS" if verdict else "FAIL"
    print(f"  {passed} passed, {failed} failed  ->  [{outcome}]")
    print(_check(verdict, "OVERALL VERDICT",
                 "Ready for paper trading" if verdict else "Review failures above"))

    print()
    print("-- DISCLAIMER ---------------------------------------------------")
    print("  This verification is READ-ONLY. No order or trade was submitted.")
    print(f"  Run completed at {ts}")
    print("=" * 62)

    mt5.shutdown()
    sys.exit(0 if verdict else 1)


if __name__ == "__main__":
    main()
