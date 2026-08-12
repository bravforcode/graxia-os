#!/usr/bin/env python3
"""
MT5 Portfolio Symbol Verification — 8 Target Symbols
=====================================================
Connects to Pepperstone MT5, verifies all 8 target symbols exist
with correct properties, and produces:
  - Console report
  - artifacts/portfolio/mt5_symbol_check.json
  - Meta/swap_rates.md

READ-ONLY: no orders placed.

Usage:
    python scripts/mt5_portfolio_verify.py
"""

import json
import sys
from datetime import datetime, UTC
from pathlib import Path

import MetaTrader5 as mt5

TERMINAL_PATH = r"C:\Program Files\Pepperstone MetaTrader 5\terminal64.exe"
TIMEOUT_MS = 30_000

# Target symbols — canonical name -> possible broker names
TARGET_SYMBOLS = {
    "XAUUSD":  ["XAUUSD", "XAUUSD.i", "XAUUSDm", "GOLD", "XAUUSD."],
    "EURUSD":  ["EURUSD", "EURUSD.i", "EURUSDm", "EURUSD."],
    "GBPUSD":  ["GBPUSD", "GBPUSD.i", "GBPUSDm", "GBPUSD."],
    "USDJPY":  ["USDJPY", "USDJPY.i", "USDJPYm", "USDJPY."],
    "BTCUSD":  ["BTCUSD", "BTCUSD.i", "BTCUSDm", "BTCUSD.", "BTCUSD.01"],
    "ETHUSD":  ["ETHUSD", "ETHUSD.i", "ETHUSDm", "ETHUSD."],
    "SILVER":  ["XAGUSD", "SILVER", "XAGUSD.i", "XAGUSDm", "XAGUSD.", "SILVER."],
    "OIL":     ["WTI", "OIL", "USOIL", "XTIUSD", "CRUDE", "WTI.", "OILUSD", "USOIL."],
}

SWAP_TYPE_LABELS = {
    0: "POINTS",
    1: "CURRENCY_SYMBOL",
    2: "INTEREST_CURRENCY",
    3: "MARGIN_CURRENCY",
}

DAY_LABELS = ["SUN", "MON", "TUE", "WED", "THU", "FRI", "SAT"]


def _fmt_swap(swap_val, swap_type, point):
    """Format swap value into human-readable string."""
    if swap_val == 0:
        return "0"
    type_label = SWAP_TYPE_LABELS.get(swap_type, f"TYPE_{swap_type}")
    if swap_type == 0:  # points
        return f"{swap_val:.2f} pts ({swap_val * point:.4f} per unit)"
    return f"{swap_val:.4f} ({type_label})"


def main() -> None:
    ts = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    print("=" * 70)
    print("  MT5 PORTFOLIO SYMBOL VERIFICATION — 8 TARGET SYMBOLS")
    print(f"  Run at {ts}")
    print("=" * 70)

    # 1. Init MT5
    init_ok = mt5.initialize(path=TERMINAL_PATH, timeout=TIMEOUT_MS)
    if not init_ok:
        err = mt5.last_error()
        print(f"\n  [FAIL] MT5 init failed: {err}")
        print("  SUGGESTIONS:")
        print("  - Ensure MT5 terminal is running")
        print("  - Check terminal path:", TERMINAL_PATH)
        print("  - Try restarting MT5")
        mt5.shutdown()
        sys.exit(1)
    print(f"\n  [OK] MT5 initialized — terminal: {TERMINAL_PATH}")

    # 2. Account info
    account = mt5.account_info()
    if account is None:
        print("  [FAIL] Cannot read account info")
        mt5.shutdown()
        sys.exit(1)

    server_lower = (account.server or "").lower()
    is_demo = "demo" in server_lower or "contest" in server_lower
    account_type = "DEMO" if is_demo else "REAL"

    print("\n  ACCOUNT:")
    print(f"    Server:   {account.server}")
    print(f"    Login:    {account.login}")
    print(f"    Type:     {account_type}")
    print(f"    Balance:  ${account.balance:,.2f}")
    print(f"    Equity:   ${account.equity:,.2f}")
    print(f"    Leverage: 1:{account.leverage}")
    print(f"    Currency: {account.currency}")

    # 3. Get all available symbols
    all_symbols = mt5.symbols_get()
    all_names = sorted([s.name for s in all_symbols]) if all_symbols else []
    print(f"\n  Total symbols available: {len(all_names)}")

    # 4. Verify each target symbol
    results = {}
    found_symbols = []
    not_found_symbols = []
    swap_data = {}

    for canonical, candidates in TARGET_SYMBOLS.items():
        print(f"\n  --- {canonical} ---")
        matched_name = None

        # Try each candidate name
        for candidate in candidates:
            if candidate in all_names:
                matched_name = candidate
                break

        if matched_name is None:
            # Fuzzy search
            fuzzy = [n for n in all_names if canonical[:3] in n.upper()]
            print(f"    [NOT FOUND] None of {candidates} in symbol list")
            if fuzzy:
                print(f"    [HINT] Partial matches: {fuzzy[:10]}")
            not_found_symbols.append(canonical)
            results[canonical] = {
                "status": "NOT_FOUND",
                "candidates_tried": candidates,
                "partial_matches": fuzzy[:10],
            }
            continue

        # Select and get info
        mt5.symbol_select(matched_name, True)
        sym = mt5.symbol_info(matched_name)
        tick = mt5.symbol_info_tick(matched_name)

        if sym is None:
            print(f"    [FAIL] {matched_name} found but symbol_info returned None")
            not_found_symbols.append(canonical)
            results[canonical] = {"status": "INFO_ERROR", "matched_name": matched_name}
            continue

        # Spread
        spread_points = round((tick.ask - tick.bid) / sym.point) if sym.point > 0 and tick else 0
        spread_price = round(tick.ask - tick.bid, 5) if tick else 0

        # Swap
        swap_long = getattr(sym, "swap_long", 0)
        swap_short = getattr(sym, "swap_short", 0)
        swap_type = getattr(sym, "swap_mode", 0)

        # Trading sessions — get today's session
        weekday = datetime.now(UTC).weekday()
        sessions = []
        try:
            for i in range(7):
                sess = mt5.symbol_info_session(symbol=matched_name, weekday=i, index=0) if hasattr(mt5, 'symbol_info_session') else None
                if sess:
                    sessions.append(f"{DAY_LABELS[i]}: {sess}")
        except Exception:
            sessions = ["session query not supported"]

        sym_data = {
            "status": "FOUND",
            "matched_name": matched_name,
            "canonical": canonical,
            "description": sym.description,
            "bid": tick.bid if tick else None,
            "ask": tick.ask if tick else None,
            "spread_points": spread_points,
            "spread_price": spread_price,
            "point": sym.point,
            "digits": sym.digits,
            "volume_min": sym.volume_min,
            "volume_max": sym.volume_max,
            "volume_step": sym.volume_step,
            "contract_size": getattr(sym, "trade_contract_size", None),
            "swap_long": swap_long,
            "swap_short": swap_short,
            "swap_mode": swap_type,
            "swap_mode_label": SWAP_TYPE_LABELS.get(swap_type, f"TYPE_{swap_type}"),
            "trade_mode": getattr(sym, "trade_mode", None),
            "trade_stops_level": getattr(sym, "trade_stops_level", None),
            "trade_freeze_level": getattr(sym, "trade_freeze_level", None),
            "margin_initial": getattr(sym, "margin_initial", None),
            "currency_base": getattr(sym, "currency_base", None),
            "currency_profit": getattr(sym, "currency_profit", None),
        }
        found_symbols.append(canonical)
        results[canonical] = sym_data

        # Collect swap data for swap_rates.md
        swap_data[canonical] = {
            "matched_name": matched_name,
            "description": sym.description,
            "swap_long": swap_long,
            "swap_short": swap_short,
            "swap_mode": swap_type,
            "swap_mode_label": SWAP_TYPE_LABELS.get(swap_type, f"TYPE_{swap_type}"),
            "point": sym.point,
            "contract_size": getattr(sym, "trade_contract_size", None),
        }

        # Print summary
        print(f"    Match:     {matched_name} ({sym.description})")
        print(f"    Spread:    {spread_points} pts / ${spread_price}")
        print(f"    Lot range: {sym.volume_min} — {sym.volume_max} (step {sym.volume_step})")
        print(f"    Contract:  {getattr(sym, 'trade_contract_size', 'N/A')}")
        print(f"    Swap Long: {_fmt_swap(swap_long, swap_type, sym.point)}")
        print(f"    Swap Short:{_fmt_swap(swap_short, swap_type, sym.point)}")
        print(f"    Stops Lvl: {getattr(sym, 'trade_stops_level', 'N/A')} pts")
        print(f"    Digits:    {sym.digits}")

    # 5. Summary
    print(f"\n{'=' * 70}")
    print("  SUMMARY")
    print(f"  Found:     {len(found_symbols)}/8 — {found_symbols}")
    print(f"  Not found: {len(not_found_symbols)}/8 — {not_found_symbols if not_found_symbols else 'None'}")
    print(f"{'=' * 70}")

    # 6. Save JSON
    output = {
        "verification_time": ts,
        "account": {
            "server": account.server,
            "login": account.login,
            "type": account_type,
            "balance": account.balance,
            "leverage": f"1:{account.leverage}",
            "currency": account.currency,
        },
        "total_broker_symbols": len(all_names),
        "target_count": len(TARGET_SYMBOLS),
        "found_count": len(found_symbols),
        "not_found_count": len(not_found_symbols),
        "found_symbols": found_symbols,
        "not_found_symbols": not_found_symbols,
        "symbol_details": results,
    }

    json_path = Path(r"C:\Users\menum\graxia os\graxia\packages\quant_os\artifacts\portfolio\mt5_symbol_check.json")
    json_path.write_text(json.dumps(output, indent=2, default=str), encoding="utf-8")
    print(f"\n  [SAVED] {json_path}")

    # 7. Write swap_rates.md
    swap_path = Path(r"C:\Users\menum\graxia os\graxia\packages\quant_os\Meta\swap_rates.md")
    md_lines = [
        "# Swap Rates — Pepperstone Demo (MT5)",
        "",
        f"**Verified:** {ts}",
        f"**Account:** {account.login} ({account.server})",
        "",
        "## Symbol Swap Table",
        "",
        "| Symbol | Broker Name | Swap Long | Swap Short | Swap Mode |",
        "|--------|-------------|-----------|------------|-----------|",
    ]

    for canonical in TARGET_SYMBOLS:
        if canonical in swap_data and canonical in found_symbols:
            sd = swap_data[canonical]
            sl = _fmt_swap(sd["swap_long"], sd["swap_mode"], sd["point"])
            ss = _fmt_swap(sd["swap_short"], sd["swap_mode"], sd["point"])
            md_lines.append(
                f"| {canonical} | {sd['matched_name']} | {sl} | {ss} | {sd['swap_mode_label']} |"
            )
        else:
            md_lines.append(f"| {canonical} | NOT FOUND | — | — | — |")

    md_lines += [
        "",
        "## Swap Calculation Notes",
        "",
        "- **Swap mode POINTS**: swap value is in points. Multiply by `point` to get price difference per lot per day.",
        "- **3x Wednesday**: Most brokers charge 3x swap on Wednesday to account for weekend settlement.",
        "- **Long = swap_long**: charged/credited when holding a BUY position overnight.",
        "- **Short = swap_short**: charged/credited when holding a SELL position overnight.",
        "",
        "## Per-Symbol Details",
        "",
    ]

    for canonical in TARGET_SYMBOLS:
        if canonical in swap_data and canonical in found_symbols:
            sd = swap_data[canonical]
            md_lines.append(f"### {canonical} ({sd['matched_name']})")
            md_lines.append(f"- Description: {sd['description']}")
            md_lines.append(f"- Swap Long: {_fmt_swap(sd['swap_long'], sd['swap_mode'], sd['point'])}")
            md_lines.append(f"- Swap Short: {_fmt_swap(sd['swap_short'], sd['swap_mode'], sd['point'])}")
            md_lines.append(f"- Swap Mode: {sd['swap_mode_label']}")
            if sd["contract_size"]:
                md_lines.append(f"- Contract Size: {sd['contract_size']}")
            md_lines.append("")

    md_lines.append(f"\n---\n*Auto-generated by mt5_portfolio_verify.py — {ts}*\n")
    swap_path.write_text("\n".join(md_lines), encoding="utf-8")
    print(f"  [SAVED] {swap_path}")

    # 8. Disconnect
    mt5.shutdown()

    # Exit code
    if not_found_symbols:
        print(f"\n  [WARN] {len(not_found_symbols)} symbol(s) not found. Review above.")
        sys.exit(1)
    else:
        print("\n  [PASS] All 8 symbols verified successfully.")
        sys.exit(0)


if __name__ == "__main__":
    main()
