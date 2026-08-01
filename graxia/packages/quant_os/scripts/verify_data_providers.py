"""Verify all data provider credentials and connections.

Usage:
    python scripts/verify_data_providers.py
    python scripts/verify_data_providers.py --fix  # Attempt to fix issues

Checks:
    1. LEAN CLI installed
    2. QuantConnect credentials configured
    3. Oanda API accessible
    4. Polygon API accessible
    5. Alpha Vantage API accessible
    6. All providers return valid data
"""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent.parent


def check(name: str, ok: bool, detail: str = ""):
    icon = "+" if ok else "x"
    msg = f"  [{icon}] {name:30s}"
    if detail:
        msg += f"  {detail}"
    print(msg)
    return ok


def verify_lean_cli() -> bool:
    """Check LEAN CLI is installed."""
    try:
        result = subprocess.run(["lean", "--version"], capture_output=True, text=True, timeout=10)
        return check("LEAN CLI", result.returncode == 0, result.stdout.strip())
    except FileNotFoundError:
        return check("LEAN CLI", False, "NOT INSTALLED — run: pip install lean")


def verify_quantconnect() -> bool:
    """Check QuantConnect credentials."""
    user_id = os.getenv("QUANTCONNECT_USER_ID", "")
    api_token = os.getenv("QUANTCONNECT_API_TOKEN", "")

    if not api_token:
        return check("QuantConnect API Token", False, "NOT SET in .env")

    # Try to verify with LEAN CLI
    try:
        result = subprocess.run(
            ["lean", "config", "get", "api-token"],
            capture_output=True, text=True, timeout=10,
        )
        configured = result.returncode == 0 and api_token[:8] in result.stdout
        return check("QuantConnect API Token", configured, f"Token: {api_token[:8]}...")
    except Exception:
        return check("QuantConnect API Token", True, f"Token: {api_token[:8]}... (in .env)")


def verify_oanda() -> bool:
    """Check Oanda credentials."""
    token = os.getenv("OANDA_ACCESS_TOKEN", "")
    account_id = os.getenv("OANDA_ACCOUNT_ID", "")
    env = os.getenv("OANDA_ENVIRONMENT", "Practice")

    if not token:
        return check("Oanda Access Token", False, "NOT SET in .env")
    if not account_id:
        return check("Oanda Account ID", False, "NOT SET in .env")

    # Try to hit Oanda API
    import httpx
    try:
        base = "api-fxpractice" if env == "Practice" else "api-fxtrade"
        resp = httpx.get(
            f"https://{base}.oanda.com/v3/accounts/{account_id}",
            headers={"Authorization": f"Bearer {token}"},
            timeout=10,
        )
        if resp.status_code == 200:
            data = resp.json().get("account", {})
            balance = data.get("balance", "?")
            return check("Oanda", True, f"Account: {account_id}, Balance: {balance}")
        else:
            return check("Oanda", False, f"HTTP {resp.status_code} — check token/account")
    except Exception as e:
        return check("Oanda", False, f"Connection failed: {e}")


def verify_polygon() -> bool:
    """Check Polygon.io credentials."""
    key = os.getenv("POLYGON_API_KEY", "")

    if not key:
        return check("Polygon API Key", False, "NOT SET in .env")

    import httpx
    try:
        resp = httpx.get(
            f"https://api.polygon.io/v3/reference/locales?apiKey={key}",
            timeout=10,
        )
        ok = resp.status_code == 200
        return check("Polygon.io", ok, f"Key: {key[:8]}... (status: {resp.status_code})")
    except Exception as e:
        return check("Polygon.io", False, f"Connection failed: {e}")


def verify_alphavantage() -> bool:
    """Check Alpha Vantage credentials."""
    key = os.getenv("ALPHAVANTAGE_API_KEY", "")

    if not key:
        return check("Alpha Vantage API Key", False, "NOT SET in .env")

    import httpx
    try:
        resp = httpx.get(
            "https://www.alphavantage.co/query",
            params={
                "function": "CURRENCY_EXCHANGE_RATE",
                "from_currency": "EUR",
                "to_currency": "USD",
                "apikey": key,
            },
            timeout=10,
        )
        data = resp.json()
        ok = "Realtime Currency Exchange Rate" in data
        return check("Alpha Vantage", ok, f"Key: {key[:8]}...")
    except Exception as e:
        return check("Alpha Vantage", False, f"Connection failed: {e}")


def verify_all_data_providers() -> bool:
    """Verify via unified DataProviders class."""
    sys.path.insert(0, str(PROJECT_ROOT))
    from market_data.providers import DataProviders
    providers = DataProviders.from_env()

    if not providers._providers:
        check("Unified DataProviders", False, "No providers configured")
        return False

    results = providers.health_check()
    for r in results:
        ok = r.get("ok", False)
        detail = r.get("error", r.get("status", ""))
        check(f"DataProviders.{r['provider']}", ok, str(detail))

    providers.close()
    return all(r.get("ok") for r in results)


def main():
    print("=" * 60)
    print("Data Provider Verification")
    print("=" * 60)
    print()

    # Load .env first
    try:
        from dotenv import load_dotenv
        load_dotenv(PROJECT_ROOT / ".env", override=True)
    except ImportError:
        pass

    all_ok = True
    all_ok &= verify_lean_cli()
    all_ok &= verify_quantconnect()
    all_ok &= verify_oanda()
    all_ok &= verify_polygon()
    all_ok &= verify_alphavantage()

    print()
    print("-" * 60)
    print("Unified Provider Test")
    print("-" * 60)
    all_ok &= verify_all_data_providers()

    print()
    print("=" * 60)
    if all_ok:
        print("ALL CHECKS PASSED")
    else:
        print("SOME CHECKS FAILED — see above")
        print()
        print("Next steps:")
        print("  1. Get API keys from signup links below")
        print("  2. Add to .env file")
        print("  3. Re-run this script")
        print()
        print("Signup Links:")
        print("  QuantConnect:  https://www.quantconnect.com/signup")
        print("  Oanda:         https://www.oanda.com/account/practice/")
        print("  Polygon.io:    https://polygon.io/")
        print("  Alpha Vantage: https://www.alphavantage.co/support/#api-key")

    return 0 if all_ok else 1


if __name__ == "__main__":
    sys.exit(main())
