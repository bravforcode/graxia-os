# Revenue OS — Stripe Price ID Wiring

## 1. Stripe dashboard (founder action)
1. Stripe Dashboard → Products → Create product for each tier:
   - Revenue OS Starter — ฿499/month (recurring)
   - Revenue OS Growth — ฿1,490/month (recurring)
   - Revenue OS Scale — ฿4,900/month (recurring)
2. Copy each Price ID (`price_...`) — one per tier.

## 2. Wire into DB (run against the deployed revenue_os DB)
```sql
UPDATE revenue_os_products SET stripe_price_id = 'price_STARTER' WHERE slug = 'revenue-os-starter';
UPDATE revenue_os_products SET stripe_price_id = 'price_GROWTH' WHERE slug = 'revenue-os-growth';
UPDATE revenue_os_products SET stripe_price_id = 'price_SCALE' WHERE slug = 'revenue-os-scale';
```

## 3. Verify
- Checkout with a wired product uses `price=` (Stripe-managed) — covered by
  `test_create_checkout_session_uses_stripe_price_id`.
- Stripe dashboard → Payment links / Checkout test: complete a test payment.