"""
MT5 Connection Diagnostic and Fix Script
Phase 2: Connect to Pepperstone Razor Demo + Measure EURUSD Spread
"""
import MetaTrader5 as mt5
import os
import time
import signal
import sys

LOGIN = int(os.getenv("MT5_LOGIN", "0"))
PASSWORD = os.getenv("MT5_PASSWORD", "")
SERVER = os.getenv("MT5_SERVER", "Pepperstone-Demo")

TERMINAL_PATHS = [
    r"C:\Program Files\MetaTrader 5\terminal64.exe",
    r"C:\Program Files (x86)\MetaTrader 5\terminal64.exe",
    r"C:\Users\menum\AppData\Roaming\MetaQuotes\Terminal\D0E8207F77A8CF37AD8BF550E51FF075\terminal64.exe",
]


def try_connect():
    """Try connecting to MT5 with various methods."""

    for method_name, method_fn in [
        ("initialize()", lambda: mt5.initialize()),
        ("initialize(login=...)",
         lambda: mt5.initialize(login=LOGIN, password=PASSWORD, server=SERVER)),
    ]:
        print(f"\n--- Method: {method_name} ---")
        try:
            result = method_fn()
            print(f"  Result: {result}")
            if result:
                return True
            else:
                print(f"  Error: {mt5.last_error()}")
        except Exception as e:
            print(f"  Exception: {e}")

    return False


def try_login():
    """Once initialized, try logging in."""
    # Check current state
    info = mt5.terminal_info()
    if info:
        print(f"\n  Current terminal: {info.name}")
        print(f"  Connected: {info.connected}")
        print(f"  Community account: {info.community_account}")
        print(f"  Path: {info.path}")

    # Try login
    for server in [SERVER, "Pepperstone-MT5-Demo", "Pepperstone-Live", "Pepperstone-MT5", None]:
        srv_str = server or "(default)"
        print(f"\n  Trying login with server: {srv_str}")
        try:
            if server:
                result = mt5.login(LOGIN, password=PASSWORD, server=server)
            else:
                result = mt5.login(LOGIN, password=PASSWORD)
            print(f"  Result: {result}")
            if result:
                return True
            else:
                print(f"  Error: {mt5.last_error()}")
        except Exception as e:
            print(f"  Exception: {e}")

    return False


def measure_spread():
    """Once logged in, measure EURUSD spread."""
    print("\n=== MEASURING EURUSD SPREAD ===")

    sym = mt5.symbol_info("EURUSD")
    if sym is None:
        print("  EURUSD not found!")
        return

    print(f"  Symbol: {sym.name}")
    print(f"  Spread: {sym.spread} points")
    print(f"  Digits: {sym.digits}")
    print(f"  Point: {sym.point}")
    print(f"  Tick size: {sym.trade_tick_size}")
    print(f"  Tick value: {sym.trade_tick_value}")
    print(f"  Swap long: {sym.swap_long}")
    print(f"  Swap short: {sym.swap_short}")
    print(f"  Volume min: {sym.volume_min}")
    print(f"  Volume max: {sym.volume_max}")
    print(f"  Volume step: {sym.volume_step}")
    print(f"  Trade mode: {sym.trade_mode}")
    print(f"  Margin initial: {sym.margin_initial}")
    print(f"  Margin maintenance: {sym.margin_maintenance}")

    # Calculate spread in bps
    spread_bps = sym.spread * sym.point / (sym.bid + sym.ask) * 2 * 10000 if sym.bid and sym.ask else None
    if spread_bps:
        print(f"\n  Spread in bps (computed): {spread_bps:.2f}")

    # Account info
    account = mt5.account_info()
    if account:
        print(f"\n  Account: {account.login}")
        print(f"  Balance: {account.balance:.2f} {account.currency}")
        print(f"  Equity: {account.equity:.2f}")
        print(f"  Leverage: 1:{account.leverage}")
        print(f"  Margin free: {account.margin_free:.2f}")

    # Sample tick for spread
    tick = mt5.symbol_info_tick("EURUSD")
    if tick:
        raw_spread = tick.ask - tick.bid
        print(f"\n  Current tick:")
        print(f"  Bid: {tick.bid}")
        print(f"  Ask: {tick.ask}")
        print(f"  Raw spread: {raw_spread:.6f}")
        print(f"  Spread in points: {raw_spread / sym.point:.1f}")


def main():
    print("=" * 60)
    print("  MT5 CONNECTION FIXER - Pepperstone Razor Demo")
    print("=" * 60)

    # Step 1: Shutdown any existing connections
    try:
        mt5.shutdown()
        print("Shutdown previous connections: OK")
    except:
        pass
    time.sleep(1)

    # Step 2: Try to connect
    if not try_connect():
        print("\n" + "!" * 60)
        print("  ALL CONNECTION METHODS FAILED")
        print("!" * 60)
        print()
        print("  Troubleshooting steps:")
        print("  1. Ensure MT5 terminal is running (terminal64.exe)")
        print("  2. Login manually in the terminal first")
        print("  3. Check firewall/antivirus blocking Python-MT5 connection")
        print("  4. Try running Python as Administrator")
        print("  5. Verify MetaTrader5 Python package version matches terminal")
        return

    # Step 3: Login
    if not try_login():
        print("\n" + "!" * 60)
        print("  LOGIN FAILED")
        print("!" * 60)
        print()
        print("  Possible causes:")
        print("  1. Wrong credentials")
        print("  2. Server name mismatch")
        print("  3. Account expired/deactivated")
        print("  4. Two-factor auth required")
        mt5.shutdown()
        return

    # Step 4: Measure spread
    measure_spread()

    mt5.shutdown()
    print("\nDisconnected. Done.")


if __name__ == "__main__":
    main()
