#!/usr/bin/env python3
"""
Create Stripe products and prices for Graxia OS billing.
Run with: python scripts/setup_stripe_products.py
"""
import os
import sys

import stripe

# Use a valid test key for demo (replace with real key in production)
stripe.api_key = "sk_test_4242424242424242"

def create_products_and_prices():
    """Create Starter and Pro products with monthly prices."""

    # Create Starter product
    starter_product = stripe.Product.create(
        name="Starter",
        description="Perfect for individuals getting started with AI-powered productivity",
        metadata={"plan": "starter"},
        images=[],
    )
    print(f"✅ Created Starter product: {starter_product.id}")

    # Create Starter price ($29/month)
    starter_price = stripe.Price.create(
        product=starter_product.id,
        unit_amount=2900,  # $29.00 in cents
        currency="usd",
        recurring={"interval": "month"},
        metadata={"plan": "starter"},
        nickname="Starter Monthly",
    )
    print(f"✅ Created Starter price: {starter_price.id}")

    # Create Pro product
    pro_product = stripe.Product.create(
        name="Pro",
        description="For teams and power users who need advanced AI automation",
        metadata={"plan": "pro"},
        images=[],
    )
    print(f"✅ Created Pro product: {pro_product.id}")

    # Create Pro price ($79/month)
    pro_price = stripe.Price.create(
        product=pro_product.id,
        unit_amount=7900,  # $79.00 in cents
        currency="usd",
        recurring={"interval": "month"},
        metadata={"plan": "pro"},
        nickname="Pro Monthly",
    )
    print(f"✅ Created Pro price: {pro_price.id}")

    print("\n" + "="*60)
    print("UPDATE YOUR .env FILE WITH THESE PRICE IDs:")
    print("="*60)
    print(f"STRIPE_PRICE_STARTER={starter_price.id}")
    print(f"STRIPE_PRICE_PRO={pro_price.id}")
    print("="*60)

    return {
        "starter_product": starter_product.id,
        "starter_price": starter_price.id,
        "pro_product": pro_product.id,
        "pro_price": pro_price.id,
    }

if __name__ == "__main__":
    try:
        result = create_products_and_prices()
        print(f"\n✅ All products and prices created successfully!")
        print(f"Starter: {result['starter_product']} @ {result['starter_price']}")
        print(f"Pro: {result['pro_product']} @ {result['pro_price']}")
    except stripe.error.StripeError as e:
        print(f"❌ Stripe error: {e}")
        sys.exit(1)
    except Exception as e:
        print(f"❌ Unexpected error: {e}")
        sys.exit(1)
