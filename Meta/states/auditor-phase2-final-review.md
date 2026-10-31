# Auditor — Phase 2 Ecommerce Final Review (state)

Date: 2026-08-16
Scope: commits 8e7e40c2..22994a46 (channels, ads, pricing, backtest, celery tasks, API)
Verdict: REJECT (6 HIGH findings)

## Blocking HIGH findings
1. shopify.py:149 uses IncidentSeverity without import -> NameError; webhook path (channels.py:30) always product_id=None -> every webhook order crashes import.
2. AdCampaignSync.status never set in prod (sync_ads_metrics meta.py:101-120) -> _ads_optimization filter status=="ACTIVE" (commerce_ops.py:121) matches nothing -> ads budget/pause engine inert (tests only set status).
3. supplier_pod.py:67-70 submit failure swallowed -> SupplierOrder SUBMITTED w/o ref; poll() filters supplier_order_ref.isnot(None) (line 79) -> never retried, no incident.
4. SupplierPODAdapter.submit_order never called by prod code (only tests) -> physical fulfillment branch (fulfillment_service.py:100-108) never places supplier order.
5. Duplicate stale-product cut: _price_optimization (commerce_ops.py:62-88) + DynamicPricingEngine -10% (dynamic.py:48-49) both fire per cycle; agent path bypasses PriceChangeLock -> ~19% double cut.
6. (latent, currently masked by #2) roas=0.0 on zero-spend campaigns -> pause fires (commerce_ops.py:123-135; spend>0 guard at :136 is after pause branch).

## MEDIUM
- float->int truncation on money: shopify.py:109, channels.py:28, meta.py:86 (19.99->1998)
- _ads_optimization Meta calls uncaught -> run_cycle/ads_sync task fails mid-cycle, work lost
- two hourly writers (commerce-ops + ads-sync) different locks, cumulative ±19%/hr
- TOCTOU on PriceChangeLock check-then-set (dynamic.py:55-84)
- supplier margin/cost + ads ABSOLUTE cap currency mixing (hardcoded THB, commerce_ops.py:149)
- supplier_cost_cents missing -> margin 100% -> policy passes
- fulfill_order commits mid-batch (fulfillment_service.py:121) -> non-atomic import
- backtest baseline_revenue_cents hardcoded 0 -> estimates meaningless (backtest.py:62)
- PolicyEngine.get_autonomy_mode commits inside check (policy_engine.py:39)

## Verified OK
- HMAC verify-before-parse, compare_digest (shopify/supplier); admin auth constant-time, prod fail-fast
- new_budget ±10% clamp math verified (10000->9000)
- lock TTL 600 >= task hard limit 360; metrics failure returns skipped; SHADOW never calls external APIs
- reconcile direction rules (no downgrade REFUNDED/CANCELLED)
- all SQLAlchemy bound params (no SQLi); no secrets logged
