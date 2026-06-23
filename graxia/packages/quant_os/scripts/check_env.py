#!/usr/bin/env python3
"""Phase 0A MT5 environment policy check.

This script is guidance-only. It does not change runtime behavior.
"""

from __future__ import annotations

import os
import sys


FORBIDDEN_ENV_KEYS = ("MT5_LOGIN", "MT5_PASSWORD", "MT5_SERVER")
ALLOWED_ENV_KEYS = ("MT5_PATH", "MT5_TIMEOUT_MS")


def main() -> int:
    forbidden = [key for key in FORBIDDEN_ENV_KEYS if os.getenv(key, "").strip()]
    mt5_path = os.getenv("MT5_PATH", "").strip()
    mt5_timeout_ms = os.getenv("MT5_TIMEOUT_MS", "").strip() or "10000"

    print("Phase 0A MT5 environment check")
    print("Policy: terminal-session-only authentication; no repo-owned MT5 secrets.")
    print(f"Allowed env keys: {', '.join(ALLOWED_ENV_KEYS)}")
    print("Broker identity source: non-secret broker profile metadata.")

    if forbidden:
        print("")
        print("FAIL")
        print(
            "Deprecated env keys detected: "
            + ", ".join(forbidden)
        )
        print("Remove MT5_LOGIN/MT5_PASSWORD/MT5_SERVER from repo-owned paths.")
        print("Log into the MT5 terminal interactively on the host machine instead.")
        return 1

    print("")
    print("PASS")
    print(f"MT5_PATH={mt5_path or '<unset>'}")
    print(f"MT5_TIMEOUT_MS={mt5_timeout_ms}")
    print("Expected broker identity fields: profile_id, expected_server, account_mode, account_currency, account_login")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
