#!/usr/bin/env python3
"""
Generate secure random keys for Quant OS
Run this on Windows since openssl is not available by default
"""

import secrets
import sys


def generate_key(length=32):
    """Generate a secure random hex key"""
    return secrets.token_hex(length)


def main():
    print("=" * 70)
    print("Quant OS Key Generator")
    print("=" * 70)
    print()
    
    # Generate keys
    jwt_secret = generate_key(32)
    webhook_secret = generate_key(32)
    admin_key = generate_key(32)
    
    print("Copy these into your .env file:")
    print()
    print("# JWT Secret (for API authentication)")
    print(f"JWT_SECRET_KEY={jwt_secret}")
    print()
    print("# Webhook HMAC Secret (for TradingView webhook verification)")
    print(f"WEBHOOK_HMAC_SECRET={webhook_secret}")
    print()
    print("# Admin API Key (for emergency/admin operations)")
    print(f"ADMIN_API_KEY={admin_key}")
    print()
    print("=" * 70)
    print("IMPORTANT: Keep these secret! Never commit them to git.")
    print("=" * 70)
    
    # Optionally write to .env file
    if len(sys.argv) > 1 and sys.argv[1] == "--update-env":
        try:
            with open(".env", "r") as f:
                content = f.read()
            
            # Replace existing keys
            content = content.replace(
                "JWT_SECRET_KEY=change_this_to_a_64_char_hex_string",
                f"JWT_SECRET_KEY={jwt_secret}"
            )
            content = content.replace(
                "WEBHOOK_HMAC_SECRET=change_this_for_webhook_hmac_verification",
                f"WEBHOOK_HMAC_SECRET={webhook_secret}"
            )
            content = content.replace(
                "ADMIN_API_KEY=change_this_admin_key_for_emergency_operations",
                f"ADMIN_API_KEY={admin_key}"
            )
            
            with open(".env", "w") as f:
                f.write(content)
            
            print("\n.env file updated with new keys!")
        except FileNotFoundError:
            print("\n.env file not found. Keys displayed above.")


if __name__ == "__main__":
    main()
