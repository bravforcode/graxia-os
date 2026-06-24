# Closure Period Campaign — 2026-06-24

## Status: Infrastructure / Plumbing Validation Only

Source: `C:\Users\menum\graxia os\shadow_results\pepperstone_campaign_20260624_052916.json`

Per **Master Plan Rule 2.4**: "Campaign results gathered during weekend closure or
market-closed sessions are infrastructure tests only, not strategy qualification
evidence."

This campaign ran during a weekend market closure (Asian session on XAUUSD). All
strategy-facing metrics are **invalid** for qualification purposes.

---

## Valid Inferences (Infrastructure/Plumbing)

| Area | What Was Exercised |
|------|-------------------|
| **Gate behavior** | Signal gating pipeline accepted 219 / 1183 signals (18.5% acceptance rate) |
| **Ledger validation** | Ledger sealed with hash `96a71cab...` — chain integrity verified (`ledger_valid: true`) |
| **Rejection flow** | 964 signals rejected with reason `NO_CANONICAL_TICKS` — tick canonicality gate worked correctly during closure |
| **Observability** | All metrics populated: spread percentiles (p50=0.22, p95=0.23, p99=0.31), PnL, cost, rejection breakdown |
| **No data corruption** | 219 ledger entries created with valid hash chain — no hash breaks, no missing entries |

---

## NOT Valid to Infer

| Metric | Why |
|--------|-----|
| Strategy performance | Market closed — PnL is artificial, not derived from executable prices |
| PnL interpretation | -39.32 hypothetical PnL is meaningless without live spread/execution |
| Expectancy | Requires live market conditions and slippage model |
| Win-rate | Not computable from closure-period data |
| Signal quality | Rejection was dominated by tick absence, not signal logic |
| Spread behaviour | 0.22–0.31 pip spread range is likely static/fallback during closure |

---

## Campaign Statistics

| Metric | Value |
|--------|-------|
| Total signals | 1,183 |
| Accepted | 219 |
| Rejected | 964 |
| Rejection reason | `NO_CANONICAL_TICKS` (964 / 100%) |
| Acceptance rate | 18.5% |
| Hypothetical PnL | -39.32 |
| Cost (total) | 71.53 |
| Ledger valid | Yes |
| Session type | Asian |
| Symbol | XAUUSD |

---

## Recommendation

No action needed. All infrastructure systems (gate, ledger, rejection, telemetry)
performed nominally. This campaign contributes zero evidence toward strategy
qualification per Rule 2.4. Run a live-session campaign for strategy evaluation.
