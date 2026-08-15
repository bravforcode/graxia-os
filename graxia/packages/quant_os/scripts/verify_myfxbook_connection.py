"""
Verify the Myfxbook connection end-to-end.

Run AFTER setting MYFXBOOK_EMAIL / MYFXBOOK_PASSWORD (and optionally
ACCOUNT_DATA_SOURCE=myfxbook) in the environment:

    $env:MYFXBOOK_EMAIL="you@example.com"
    $env:MYFXBOOK_PASSWORD="your_password"
    python scripts/verify_myfxbook_connection.py

Exit code 0 = connection succeeded (data fetch succeeds when accounts are
linked); 1 = connection failed (message printed).
No secrets are printed; emails/sessions are masked.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

_QUANT_OS = Path(__file__).resolve().parent.parent          # quant_os/
_PACKAGES = _QUANT_OS.parent                                # packages/

# Add packages/ so Python recognises quant_os as a subpackage of graxia
# (required for relative imports like ...core.enums inside execution/adapters).
sys.path.insert(0, str(_PACKAGES))

from quant_os.broker.myfxbook_gateway import (
    MyfxbookError,
    MyfxbookGateway,
)
from quant_os.execution.adapters.myfxbook import MyfxbookAdapter


def _mask(value: str, visible: int = 3) -> str:
    if not value:
        return ""
    return value[:visible] + "*" * max(0, len(value) - visible)


def main() -> int:
    email = os.getenv("MYFXBOOK_EMAIL", "")
    if not email or not os.getenv("MYFXBOOK_PASSWORD"):
        print("[FAIL] Set MYFXBOOK_EMAIL and MYFXBOOK_PASSWORD before running.")
        return 1

    print(f"[*] Connecting to Myfxbook as {_mask(email, 3)} ...")
    try:
        gw = MyfxbookGateway()
        session = gw.login()
        print(f"[OK] Authenticated. session={_mask(session, 4)} (IP-bound, ~30d TTL)")

        accounts = gw.get_my_accounts()
        print(f"[OK] Linked accounts: {len(accounts)}")
        for acct in accounts:
            print(
                f"      - id={acct.get('id')} name={acct.get('name')!r} "
                f"balance={acct.get('balance')} equity={acct.get('equity')} "
                f"currency={acct.get('currency')} demo={acct.get('demo')}"
            )

        if not accounts:
            print("[WARN] No trading accounts are linked to this Myfxbook profile.")
            print("       Link an MT4/MT5 account at https://www.myfxbook.com/settings#accounts")
            print("       then re-run to pull live analytics.")
            gw.logout()
            print("[OK] Connection verified (no data to fetch yet).")
            return 0

        adapter = MyfxbookAdapter(gateway=gw)
        info = adapter.get_account_info()
        print(f"[OK] AccountInfo -> equity={info.equity} cash={info.cash} "
              f"margin_used={info.margin_used} margin_available={info.margin_available}")

        positions = adapter.get_positions()
        print(f"[OK] Open positions: {len(positions)}")
        for p in positions:
            print(f"      - {p['side']} {p['symbol']} qty={p['quantity']} @ {p['avg_price']}")

        gw.logout()
        print("[OK] Logged out. Connection verified.")
        return 0
    except MyfxbookError as exc:
        print(f"[FAIL] Myfxbook error: {exc}")
        return 1
    except Exception as exc:  # pragma: no cover - defensive
        print(f"[FAIL] Unexpected error: {exc}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
