# Ads Budgets Runbook (Phase 2)

## Policy (Gate 0 defaults — edit via `/api/policy/rules`, admin)

| Rule | Cap | Meaning |
|---|---|---|
| AD_BUDGET PERCENT MAX | 10.0 | max daily budget change per action = ±10% |
| AD_BUDGET ABSOLUTE MAX | 50,000 THB cents | max absolute change per action |
| (LIMITED mode) | × 0.25 | effective caps in LIMITED = ±2.5% / 12,500 cents |

## ROAS rules (agent behavior)

| ROAS | Action |
|---|---|
| < 1.0 | **Pause** campaign (CAMPAIGN_PAUSE allow rule) |
| 1.0 – 2.0 | Cut budget toward target (clamped to ±10%) |
| 2.0 – 4.0 | Hold (within noise tolerance) |
| > 4.0 | Raise budget toward target (clamped to ±10%) |

Target ROAS constant: `AD_TARGET_ROAS = 3.0` (`agents/commerce_ops.py`).

## Kill procedure (any sign of trouble)

1. `POST /api/autonomy/mode {"mode": "off"}` with `X-Admin-Api-Key` — agents stop
   immediately; the store keeps selling.
2. Re-sync to see ground truth: `POST /api/ads/refresh` (admin).
3. If budgets were changed wrongly, set them back manually in Meta Ads Manager,
   then re-walk the rollout from SHADOW (see `docs/runbooks/autonomy-rollout.md`).

## Expected behavior in each autonomy stage

- **OFF**: ads metrics sync only — budgets never touched.
- **SHADOW**: proposals logged (`agent.*.shadow` / audit), Meta API never called.
- **LIMITED**: budget changes allowed at 25% of policy caps.
- **FULL**: full policy caps.

## Monitoring

- `ads-sync` beat job runs hourly (locked) — check its result dict
  (`actions`/`denials`/`proposals`) in Celery.
- Every denied budget change raises IncidentEvent MEDIUM → Telegram alerter pages.
- Circuit breaker (5 MEDIUM+ incidents / 60 min) force-disables autonomy.
