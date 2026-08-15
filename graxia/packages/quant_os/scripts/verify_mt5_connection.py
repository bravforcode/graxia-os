"""Verify quant_os can read the live MT5 account directly (no myfxbook EA needed).

Connects to the already-running, already-logged-in MT5 terminal and reads
account state through the repo's own read-only gateway (broker/mt5_gateway.py).
This is the better path vs myfxbook: no EA install, no DLL, no account linking.

Usage:
    python scripts/verify_mt5_connection.py
"""
import os
import sys

# Make the quant_os package importable.
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

import MetaTrader5 as mt5
from broker.mt5_gateway import get_account_info, Mt5UnavailableError


def main() -> int:
    print("[*] Initializing MT5 (connects to running terminal)...")
    if not mt5.initialize():
        print("[FAIL] mt5.initialize():", mt5.last_error())
        return 1

    try:
        ti = mt5.terminal_info()
        print("[OK] Terminal path :", getattr(ti, "path", "n/a"))

        # Raw read (sanity)
        ai = mt5.account_info()
        if ai is None:
            print("[FAIL] mt5.account_info() returned None")
            return 1
        print("[OK] Raw account  : login=%s server=%s balance=%.2f %s"
              % (ai.login, ai.server, ai.balance, ai.currency))

        # Through the repo's own read-only gateway (Contract B source)
        try:
            info = get_account_info()
            print("[OK] broker.mt5_gateway.get_account_info():")
            for k, v in info.items():
                print("       %-14s %s" % (k, v))
        except Mt5UnavailableError as e:
            print("[FAIL] gateway:", e)
            return 1

        print("\n[DONE] Live MT5 account read succeeded via the repo's own MT5 line.")
        return 0
    finally:
        mt5.shutdown()


if __name__ == "__main__":
    sys.exit(main())
