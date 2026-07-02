#!/usr/bin/env python3
"""
MT5 Crypto CFD Validation — Multi-Asset Preflight
====================================================
Connects to Pepperstone MT5, validates BTCUSD and ETHUSD CFD availability,
checks lot sizes, spread, commission, margin, and trading hours.
Outputs a JSON report to reports/mt5_crypto_validation.json.

Usage:
    python scripts/validate_mt5_crypto.py
    python scripts/validate_mt5_crypto.py --symbols BTCUSD,ETHUSD,XAUUSD,EURUSD
    python scripts/validate_mt5_crypto.py --lot-size 0.01
    python scripts/validate_mt5_crypto.py --output reports/custom_report.json
"""

import argparse
import json
import os
import sys
from datetime import UTC, datetime
from typing import Any

# ---------------------------------------------------------------------------
# MT5 lazy import
# ---------------------------------------------------------------------------
try:
    import MetaTrader5 as mt5
except ImportError:
    mt5 = None  # type: ignore[assignment]

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEFAULT_OUTPUT = os.path.join(PROJECT_ROOT, "reports", "mt5_crypto_validation.json")

# ---------------------------------------------------------------------------
# MT5 constants
# ---------------------------------------------------------------------------
TERMINAL_PATH = r"C:\Program Files\Pepperstone MetaTrader 5\terminal64.exe"
TIMEOUT_MS = 30_000

EXECUTION_LABELS = {
    0: "REQUEST",
    1: "INSTANT",
    2: "MARKET",
    3: "EXCHANGE",
}

TRADE_MODE_LABELS = {
    0: "DISABLED",
    1: "LONGONLY",
    2: "SHORTONLY",
    3: "CLOSEONLY",
    4: "FULL",
}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _fmt_dollars(val: float) -> str:
    return f"${val:,.2f}"


def _safe_float(val: Any) -> float:
    """Convert numeric value to float, return 0.0 on failure."""
    if val is None:
        return 0.0
    try:
        return float(val)
    except (ValueError, TypeError):
        return 0.0


def _check(condition: bool, label: str, detail: str = "") -> dict:
    """Build a check result dict."""
    return {
        "status": "PASS" if condition else "FAIL",
        "label": label,
        "detail": detail,
    }


def _info(label: str, value: Any) -> dict:
    """Build an info entry."""
    return {"label": label, "value": str(value)}


# ---------------------------------------------------------------------------
# Core validation
# ---------------------------------------------------------------------------
def validate_symbol(symbol: str, lot_size: float) -> dict:
    """
    Validate a single symbol on MT5. Returns a structured report for the symbol.
    """
    result: dict[str, Any] = {
        "symbol": symbol,
        "available": False,
        "checks": [],
        "info": [],
        "tick": None,
        "contract_spec": None,
        "trading_hours": None,
    }

    # --- Symbol availability ---
    symbols_list = mt5.symbols_get()
    symbol_names = [s.name for s in symbols_list] if symbols_list else []
    found = symbol in symbol_names

    result["checks"].append(
        _check(
            found,
            f"{symbol} available in MT5 symbol list",
            f"{len(symbol_names)} symbols total",
        )
    )

    if not found:
        # Search for partial matches
        partial = [s for s in symbol_names if symbol.replace("USD", "") in s]
        if partial:
            result["info"].append(_info("Similar symbols found", ", ".join(partial[:10])))
        return result

    result["available"] = True

    # --- Select symbol ---
    select_ok = mt5.symbol_select(symbol, True)
    result["checks"].append(_check(select_ok, f"{symbol} selected in Market Watch"))

    if not select_ok:
        return result

    # --- Symbol info ---
    sym = mt5.symbol_info(symbol)
    sym_ok = sym is not None
    result["checks"].append(_check(sym_ok, f"{symbol} symbol_info readable"))

    if not sym_ok:
        return result

    # Contract specification
    contract = {
        "digits": sym.digits,
        "point": _safe_float(sym.point),
        "trade_contract_size": _safe_float(sym.trade_contract_size),
        "trade_tick_size": _safe_float(sym.trade_tick_size),
        "trade_tick_value": _safe_float(sym.trade_tick_value),
        "volume_min": _safe_float(sym.volume_min),
        "volume_max": _safe_float(sym.volume_max),
        "volume_step": _safe_float(sym.volume_step),
        "stops_level": getattr(sym, "trade_stops_level", None),
        "freeze_level": getattr(sym, "trade_freeze_level", None),
        "currency_base": getattr(sym, "currency_base", ""),
        "currency_profit": getattr(sym, "currency_profit", ""),
        "currency_margin": getattr(sym, "currency_margin", ""),
        "trade_mode": TRADE_MODE_LABELS.get(getattr(sym, "trade_mode", -1), "UNKNOWN"),
        "filling_mode": getattr(sym, "filling_mode", None),
        "execution_mode": EXECUTION_LABELS.get(getattr(sym, "trade_execution", -1), "UNKNOWN"),
        "swap_long": getattr(sym, "swap_long", None),
        "swap_short": getattr(sym, "swap_short", None),
        "margin_initial": getattr(sym, "margin_initial", None),
        "margin_maintenance": getattr(sym, "margin_maintenance", None),
    }
    result["contract_spec"] = contract

    # --- Volume bounds ---
    result["checks"].append(
        _check(
            contract["volume_min"] > 0,
            "Volume min > 0",
            f"min={contract['volume_min']}, max={contract['volume_max']}, step={contract['volume_step']}",
        )
    )

    result["checks"].append(
        _check(
            lot_size >= contract["volume_min"] and lot_size <= contract["volume_max"],
            f"Lot size {lot_size} within bounds",
            f"[{contract['volume_min']}, {contract['volume_max']}] step={contract['volume_step']}",
        )
    )

    # --- Stops level ---
    stops_pts = contract["stops_level"] or 0
    point = contract["point"]
    min_stop_price = stops_pts * point if point > 0 else 0.0
    result["info"].append(_info("Stops level (points)", stops_pts))
    result["info"].append(_info("Freeze level (points)", contract["freeze_level"]))
    result["info"].append(_info("Min stop distance (price)", f"{min_stop_price:.5f}"))

    # --- Trade mode ---
    trade_mode_ok = contract["trade_mode"] in ("FULL", "LONGONLY", "SHORTONLY")
    result["checks"].append(
        _check(
            trade_mode_ok,
            "Trading enabled",
            f"mode={contract['trade_mode']}",
        )
    )

    # --- Tick data ---
    tick = mt5.symbol_info_tick(symbol)
    tick_ok = tick is not None and tick.bid > 0 and tick.ask > 0
    result["checks"].append(_check(tick_ok, f"{symbol} tick data available"))

    if tick_ok:
        spread_abs = tick.ask - tick.bid
        spread_points = round(spread_abs / point) if point > 0 else 0
        tick_data = {
            "bid": tick.bid,
            "ask": tick.ask,
            "last": tick.last,
            "spread_points": spread_points,
            "spread_absolute": round(spread_abs, 6),
            "time": tick.time,
        }
        result["tick"] = tick_data

        # Spread check — crypto CFDs typically have wider spreads
        # XAUUSD/EURUSD: <50 pts; BTCUSD/ETHUSD: <5000 pts (wider CFD spread)
        if "BTC" in symbol or "ETH" in symbol:
            spread_threshold = 5000
        elif "XAU" in symbol:
            spread_threshold = 100
        else:
            spread_threshold = 50
        spread_ok = spread_points <= spread_threshold
        result["checks"].append(
            _check(
                spread_ok,
                "Spread within threshold",
                f"{spread_points} pts (${spread_abs:.4f}) threshold={spread_threshold}",
            )
        )

        result["info"].append(_info("Bid", tick.bid))
        result["info"].append(_info("Ask", tick.ask))
        result["info"].append(_info("Spread (points)", spread_points))
        result["info"].append(_info("Spread (absolute)", f"{spread_abs:.6f}"))

    # --- Margin calculation ---
    if tick_ok and contract["margin_initial"] and contract["margin_initial"] > 0:
        margin_per_lot = contract["margin_initial"] * contract["trade_contract_size"]
        margin_for_lot = margin_per_lot * lot_size
        result["info"].append(_info("Margin per 1 lot", _fmt_dollars(margin_per_lot)))
        result["info"].append(_info(f"Margin for {lot_size} lot", _fmt_dollars(margin_for_lot)))
    elif tick_ok:
        # Fallback: use MT5 order_calc_margin
        try:
            margin = mt5.order_calc_margin(mt5.ORDER_TYPE_BUY, symbol, lot_size, tick.ask)
            if margin is not None:
                result["info"].append(_info(f"Margin for {lot_size} lot (MT5 calc)", _fmt_dollars(float(margin))))
        except Exception:
            pass

    # --- Order check (dry run) ---
    if tick_ok:
        entry = tick.ask
        sl_dist = max(stops_pts, 10) * point if point > 0 else 0.01
        for fill_type, fill_label in [(mt5.ORDER_FILLING_IOC, "IOC"), (mt5.ORDER_FILLING_FOK, "FOK")]:
            request = {
                "action": mt5.TRADE_ACTION_DEAL,
                "symbol": symbol,
                "volume": lot_size,
                "type": mt5.ORDER_TYPE_BUY,
                "price": entry,
                "sl": entry - sl_dist,
                "tp": entry + sl_dist,
                "deviation": 10,
                "magic": 999998,
                "comment": "CRYPTO_VALIDATE_DRY",
                "type_time": mt5.ORDER_TIME_GTC,
                "type_filling": fill_type,
            }
            check = mt5.order_check(request)
            if check is not None and check.retcode == 0:
                result["checks"].append(
                    _check(
                        True,
                        "Order check (dry run) passed",
                        f"fill={fill_label}",
                    )
                )
                break
        else:
            result["checks"].append(
                _check(
                    False,
                    "Order check (dry run) failed",
                    f"retcode={check.retcode if check else 'None'}",
                )
            )

    # --- Trading hours ---
    # MT5 does not expose explicit trading hours via API for CFDs.
    # Document known Pepperstone crypto CFD hours.
    if "BTC" in symbol or "ETH" in symbol:
        result["trading_hours"] = {
            "schedule": "24/7 (crypto market hours)",
            "note": "Crypto CFDs trade around the clock; spread may widen on weekends",
            "server_time": "UTC+2/+3 (broker server time)",
        }
    elif "XAU" in symbol:
        result["trading_hours"] = {
            "schedule": "Sun 22:05 - Fri 21:00 (UTC)",
            "break": "Daily break 21:00-22:05 UTC",
            "note": "Follows COMEX gold trading hours",
        }
    elif "EUR" in symbol or "GBP" in symbol or "USD" in symbol:
        result["trading_hours"] = {
            "schedule": "Sun 22:05 - Fri 21:00 (UTC)",
            "break": "Daily break 21:00-22:05 UTC",
            "note": "Follows interbank forex market hours",
        }

    return result


def validate_connection() -> dict:
    """Validate MT5 connection. Returns account info + connection status."""
    result: dict[str, Any] = {
        "connected": False,
        "account": None,
        "checks": [],
    }

    if mt5 is None:
        result["checks"].append(_check(False, "MetaTrader5 package installed", "NOT INSTALLED"))
        return result

    result["checks"].append(_check(True, "MetaTrader5 package installed"))

    # Initialize
    init_ok = mt5.initialize(path=TERMINAL_PATH, timeout=TIMEOUT_MS)
    result["checks"].append(_check(init_ok, "MT5 initialized", f"terminal={TERMINAL_PATH}"))

    if not init_ok:
        result["checks"][-1]["detail"] = f"error: {mt5.last_error()}"
        return result

    # Account info
    account = mt5.account_info()
    acct_ok = account is not None
    result["checks"].append(_check(acct_ok, "Account info readable"))

    if acct_ok:
        server_lower = (account.server or "").lower()
        is_demo = "demo" in server_lower
        result["account"] = {
            "login": account.login,
            "server": account.server,
            "balance": account.balance,
            "equity": account.equity,
            "leverage": account.leverage,
            "currency": account.currency,
            "trade_allowed": account.trade_allowed,
            "is_demo": is_demo,
        }
        result["connected"] = True
        result["checks"].append(_check(is_demo, "Account is demo/paper", f"server={account.server}"))
        result["checks"].append(_check(account.trade_allowed, "Trading enabled on account"))

    return result


def build_report(symbols: list[str], lot_size: float) -> dict:
    """Build the full validation report."""
    ts = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    report: dict[str, Any] = {
        "report_type": "mt5_crypto_validation",
        "generated_at_utc": ts,
        "lot_size_tested": lot_size,
        "connection": None,
        "symbols": {},
        "summary": {},
    }

    # Connection
    conn = validate_connection()
    report["connection"] = conn

    if not conn["connected"]:
        report["summary"] = {
            "overall": "FAIL",
            "reason": "MT5 connection failed",
            "passed": 0,
            "failed": len(conn["checks"]),
            "total_checks": len(conn["checks"]),
        }
        return report

    # Symbol validation
    all_passed = 0
    all_failed = 0
    for sym in symbols:
        sym_result = validate_symbol(sym, lot_size)
        report["symbols"][sym] = sym_result
        sym_passed = sum(1 for c in sym_result["checks"] if c["status"] == "PASS")
        sym_failed = sum(1 for c in sym_result["checks"] if c["status"] == "FAIL")
        all_passed += sym_passed
        all_failed += sym_failed

    total_checks = all_passed + all_failed
    overall = "PASS" if all_failed == 0 else "FAIL"
    report["summary"] = {
        "overall": overall,
        "passed": all_passed,
        "failed": all_failed,
        "total_checks": total_checks,
        "symbols_validated": symbols,
    }

    return report


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def main() -> None:
    parser = argparse.ArgumentParser(description="MT5 Crypto CFD Validation — multi-asset preflight")
    parser.add_argument(
        "--symbols",
        "-s",
        default="BTCUSD,ETHUSD,XAUUSD,EURUSD",
        help="Comma-separated symbols to validate (default: BTCUSD,ETHUSD,XAUUSD,EURUSD)",
    )
    parser.add_argument(
        "--lot-size",
        "-l",
        type=float,
        default=0.01,
        help="Lot size for order-check dry run (default: 0.01)",
    )
    parser.add_argument(
        "--output",
        "-o",
        default=DEFAULT_OUTPUT,
        help=f"Output JSON path (default: {DEFAULT_OUTPUT})",
    )
    args = parser.parse_args()

    symbols = [s.strip().upper() for s in args.symbols.split(",") if s.strip()]
    if not symbols:
        print("ERROR: No symbols specified")
        sys.exit(1)

    # Ensure output dir exists
    out_dir = os.path.dirname(args.output)
    if out_dir and not os.path.exists(out_dir):
        os.makedirs(out_dir, exist_ok=True)

    print(f"MT5 Crypto CFD Validation — {len(symbols)} symbols, lot={args.lot_size}")
    print("=" * 60)

    report = build_report(symbols, args.lot_size)

    # Write JSON
    with open(args.output, "w") as f:
        json.dump(report, f, indent=2, default=str)

    # Print summary
    for sym, data in report["symbols"].items():
        status_icon = "PASS" if all(c["status"] == "PASS" for c in data["checks"]) else "FAIL"
        print(f"\n[{status_icon}] {sym}")
        if data.get("tick"):
            t = data["tick"]
            print(f"  Bid={t['bid']}  Ask={t['ask']}  Spread={t['spread_points']}pts")
        for check in data["checks"]:
            icon = "  [PASS]" if check["status"] == "PASS" else "  [FAIL]"
            print(f"  {icon} {check['label']}  --  {check['detail']}")

    print(f"\n{'=' * 60}")
    s = report["summary"]
    print(f"Overall: {s['overall']}  |  Passed: {s['passed']}  Failed: {s['failed']}")

    # Shutdown MT5
    if mt5 is not None:
        try:
            mt5.shutdown()
        except Exception:
            pass

    print(f"\nReport written to: {args.output}")
    sys.exit(0 if s["overall"] == "PASS" else 1)


if __name__ == "__main__":
    main()
