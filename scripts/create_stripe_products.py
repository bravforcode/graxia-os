#!/usr/bin/env python3
"""Create Stripe subscription products + prices for Graxia OS."""
import httpx
import json
import sys

KEY = "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"
HEADERS = {"Authorization": f"Bearer {KEY}", "Content-Type": "application/x-www-form-urlencoded"}
BASE = "https://api.stripe.com/v1"

tiers = [
    ("Graxia OS Starter", "Perfect for individuals getting started with AI-powered funnel builder", "starter", 29900),
    ("Graxia OS Pro", "For teams and power users who need advanced AI automation and analytics", "pro", 79900),
    ("Graxia OS Enterprise", "Full-scale enterprise deployment with dedicated support and custom integrations", "enterprise", 199900),
]

results = {}
for name, desc, tier, amount in tiers:
    # Create product
    r = httpx.post(f"{BASE}/products", headers=HEADERS, data={
        "name": name,
        "description": desc,
        f"metadata[tier]": tier,
    })
    product = r.json()
    if not product.get("id"):
        print(f"FAILED product {tier}: {product}")
        sys.exit(1)
    print(f"Product {tier}: {product['id']}")

    # Create monthly price
    r2 = httpx.post(f"{BASE}/prices", headers=HEADERS, data={
        "product": product["id"],
        "unit_amount": str(amount),
        "currency": "thb",
        "recurring[interval]": "month",
        f"metadata[tier]": tier,
        "nickname": f"{tier.title()} Monthly",
    })
    price = r2.json()
    if not price.get("id"):
        print(f"FAILED price {tier}: {price}")
        sys.exit(1)
    print(f"Price {tier}: {price['id']}")
    results[tier] = price["id"]

print("\n=== ADD TO .env.production ===")
print(f"STRIPE_PRICE_STARTER_MONTHLY={results.get('starter', 'FAILED')}")
print(f"STRIPE_PRICE_PRO_MONTHLY={results.get('pro', 'FAILED')}")
print(f"STRIPE_PRICE_ENTERPRISE_MONTHLY={results.get('enterprise', 'FAILED')}")
