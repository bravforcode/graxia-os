#!/usr/bin/env python3
"""
Graxia OS — Environment Configuration Checker
Validates all required keys and provides setup instructions
"""
import os
import sys
from pathlib import Path

# Color codes for terminal
GREEN = "\033[92m"
RED = "\033[91m"
YELLOW = "\033[93m"
BLUE = "\033[94m"
RESET = "\033[0m"
BOLD = "\033[1m"


def check_env():
    """Check all required environment variables"""

    print(f"\n{BOLD}{'=' * 70}{RESET}")
    print(f"{BOLD}  Graxia OS — Environment Configuration Checker{RESET}")
    print(f"{BOLD}{'=' * 70}{RESET}\n")

    # Load .env if exists
    env_path = Path(".env")
    if env_path.exists():
        print(f"{BLUE}Loading .env file...{RESET}")
        with open(env_path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith('#') and '=' in line:
                    key, value = line.split('=', 1)
                    os.environ.setdefault(key, value)

    # Define required and optional keys
    checks = {
        "Database": {
            "required": [
                ("DATABASE_URL", "postgresql+asyncpg://user:pass@localhost/db"),
            ],
            "optional": []
        },
        "Security": {
            "required": [
                ("JWT_SECRET_KEY", "Random 32+ char secret"),
                ("ADMIN_API_KEY", "Random 32+ char key"),
            ],
            "optional": [
                ("WEBHOOK_HMAC_SECRET", "For TradingView webhook validation"),
            ]
        },
        "Revenue OS — Payment Gateways": {
            "required": [],
            "optional": [
                ("STRIPE_SECRET_KEY", "sk_live_... or sk_test_..."),
                ("STRIPE_WEBHOOK_SECRET", "whsec_..."),
                ("STRIPE_PUBLISHABLE_KEY", "pk_live_... or pk_test_..."),
                ("GUMROAD_API_KEY", "From Gumroad Settings > Advanced"),
                ("PAYPAL_CLIENT_ID", "From PayPal Developer Dashboard"),
                ("PAYPAL_CLIENT_SECRET", "From PayPal Developer Dashboard"),
            ]
        },
        "Quant OS — Trading": {
            "required": [
                ("TRADING_MODE", "PAPER or LIVE"),
            ],
            "optional": [
                ("LIVE_TRADING_ENABLED", "true or false"),
                ("MT5_LOGIN", "Your MetaTrader 5 account number"),
                ("MT5_PASSWORD", "Your MT5 password"),
                ("MT5_SERVER", "e.g., ICMarketsSC-Demo"),
            ]
        },
        "Notifications": {
            "required": [],
            "optional": [
                ("TELEGRAM_BOT_TOKEN", "From @BotFather"),
                ("TELEGRAM_CHAT_ID", "Your Telegram ID or group ID"),
            ]
        },
        "Infrastructure": {
            "required": [],
            "optional": [
                ("REDIS_URL", "redis://localhost:6379/0"),
                ("CORS_ORIGINS", "http://localhost:3000,..."),
                ("LOG_LEVEL", "DEBUG, INFO, WARNING, ERROR"),
            ]
        }
    }

    missing_required = []
    missing_optional = []
    present_keys = []

    for category, keys in checks.items():
        print(f"\n{BOLD}{category}{RESET}")
        print("-" * 50)

        # Check required
        for key, description in keys["required"]:
            value = os.getenv(key)
            if value and value not in ["your_key_here", "", "CHANGE_ME"]:
                print(f"  {GREEN}✓{RESET} {key}")
                present_keys.append(key)
            else:
                print(f"  {RED}✗{RESET} {key} {YELLOW}[REQUIRED]{RESET}")
                print(f"      → {description}")
                missing_required.append((key, description))

        # Check optional
        for key, description in keys["optional"]:
            value = os.getenv(key)
            if value and value not in ["your_key_here", "", "CHANGE_ME", "optional"]:
                print(f"  {GREEN}✓{RESET} {key} {BLUE}[optional]{RESET}")
                present_keys.append(key)
            else:
                print(f"  {YELLOW}○{RESET} {key} {BLUE}[optional]{RESET}")
                missing_optional.append((key, description))

    # Summary
    print(f"\n{BOLD}{'=' * 70}{RESET}")
    print(f"{BOLD}SUMMARY{RESET}")
    print(f"{BOLD}{'=' * 70}{RESET}\n")

    total_required = sum(len(v["required"]) for v in checks.values())
    total_optional = sum(len(v["optional"]) for v in checks.values())

    print(f"  Required keys present: {total_required - len(missing_required)}/{total_required}")
    print(f"  Optional keys present: {len(present_keys) - (total_required - len(missing_required))}/{total_optional}")
    print(f"  Total keys configured: {len(present_keys)}/{total_required + total_optional}")

    if missing_required:
        print(f"\n  {RED}✗ Missing {len(missing_required)} REQUIRED keys{RESET}")
        print(f"\n  {YELLOW}Add these to your .env file:{RESET}\n")
        for key, desc in missing_required:
            print(f"    {key}=your_value_here")
    else:
        print(f"\n  {GREEN}✓ All required keys configured!{RESET}")

    # Recommendations
    print(f"\n{BOLD}RECOMMENDATIONS{RESET}")
    print("-" * 50)

    if "TELEGRAM_BOT_TOKEN" not in present_keys:
        print(f"\n  {YELLOW}1. Set up Telegram notifications:{RESET}")
        print("     a. Message @BotFather on Telegram")
        print("     b. Create new bot with /newbot")
        print("     c. Copy the token to TELEGRAM_BOT_TOKEN")
        print("     d. Message @userinfobot to get your chat ID")
        print("     e. Set TELEGRAM_CHAT_ID to your ID")

    if "STRIPE_SECRET_KEY" not in present_keys:
        print(f"\n  {YELLOW}2. Set up Stripe payments:{RESET}")
        print("     a. Go to https://dashboard.stripe.com/apikeys")
        print("     b. Copy Secret key to STRIPE_SECRET_KEY")
        print("     c. Set up webhook endpoint pointing to /api/v1/revenue/webhooks/stripe")
        print("     d. Copy webhook signing secret to STRIPE_WEBHOOK_SECRET")

    if "MT5_LOGIN" not in present_keys:
        print(f"\n  {YELLOW}3. Set up MetaTrader 5:{RESET}")
        print("     a. Open MT5 and get your account number")
        print("     b. Set MT5_LOGIN to your account number")
        print("     c. Set MT5_PASSWORD to your password")
        print("     d. Set MT5_SERVER to your broker server")
        print(f"\n     {GREEN}Current TRADING_MODE: {os.getenv('TRADING_MODE', 'PAPER (safe for testing)')}{RESET}")

    # Generate sample .env
    if missing_required or missing_optional:
        print(f"\n{BOLD}QUICK FIX — Add to .env:{RESET}")
        print("-" * 50)
        for key, desc in missing_required + missing_optional[:5]:  # Show first 5 optional
            print(f"{key}=")

    print(f"\n{BOLD}{'=' * 70}{RESET}\n")

    return len(missing_required) == 0


if __name__ == "__main__":
    ok = check_env()
    sys.exit(0 if ok else 1)
