# Autonomy Rollout Runbook

How the store moves from **no automation** to **full autonomy** — safely, with observation gates between every stage.

## Stages

| Mode | What agents do |
|------|----------------|
| `off` | Nothing. Agents skip every cycle (commerce-ops logs `skipped`). |
| `shadow` | Compute + log what they WOULD do (`agent.*.shadow` AuditLog entries). **Nothing is executed.** |
| `limited` | Execute, but every MAX cap is multiplied by `limited_multiplier` (default 0.25) — e.g. a 20% price cap becomes 5%. |
| `full` | Execute at full policy-configured caps. |

## Advance procedure (manual — the ONLY way to move stages)

1. Verify current stage: `GET /api/autonomy/status` with `X-Admin-Api-Key: <key>`
2. Review readiness (daily checker writes it to StrategyLog + Telegram):
   - `ready_for_next: true` = automated gates pass
3. Complete the **manual review checklist** for the target stage (below)
4. Advance: `POST /api/autonomy/mode` with body `{"mode": "shadow" | "limited" | "full"}` and `X-Admin-Api-Key` header
5. Log the advance in your ops channel (who, when, why)

Designated operator: **one person only** (per deployment config). Never share the admin key.

## Stage gates

### OFF → SHADOW (Gate 0)
- [ ] Business owner has **confirmed or replaced every seeded policy rule** (run `POST /api/policy/seed` once, then review `GET /api/policy/rules` — defaults: price ±20%/50k THB, discount 15%/20k THB, refund 100%/1,500 THB, emails 5/day/customer)
- [ ] Full test suite green (or pre-existing baseline documented)
- [ ] `ADMIN_API_KEY` and `STRIPE_API_KEY` provisioned via secrets manager (never committed)
- [ ] Telegram notifier configured (alerter task will page you)

### SHADOW → LIMITED (Gate 1) — minimum 7 days in shadow
- [ ] Zero HIGH incidents during the window
- [ ] Average policy denials ≤ 2/day
- [ ] ≥ 10 shadow decisions logged (`AuditLog.event_type LIKE 'agent.%.shadow'`)
- [ ] **Human reviewed the shadow log** (AuditLog + StrategyLog) and approves
- [ ] Advance is documented

### LIMITED → FULL (Gate 2) — minimum 7 days in limited
- [ ] Zero HIGH incidents during the window
- [ ] Circuit breaker never tripped
- [ ] Revenue impact of LIMITED actions within ±20% of expectation (compare StrategyLog daily reports)
- [ ] **Human review passed** (audit log of all limited actions)

## Emergency: circuit breaker + re-walk

- The circuit breaker **automatically forces mode → `off`** when ≥ 5 MEDIUM+ incidents fire in 60 minutes and raises a HIGH incident (which Telegram pages).
- Any HIGH incident or breaker trip = **back to OFF**, then re-walk the stages from SHADOW.
- Do not jump OFF → FULL. The staging exists to cap blast radius while confidence is low.

## Kill switch

- `POST /api/autonomy/mode {"mode": "off"}` — agents stop immediately (store keeps selling, just unmanaged).
- `POST /api/autonomy/disable`-style shortcuts intentionally do not exist; the mode API is the single control surface.
