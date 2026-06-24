# B4 — Qualification Review Template

**Track:** B4 (Review)
**Symbol:** XAUUSD
**Broker:** Pepperstone-Demo
**Predecessor campaigns:**
- B1 (closure-period, infra-only): `CLOSURE_PERIOD_CAMPAIGN_20260624.md`
- B2 (market gate): `execution/qualification/market_gate.py`
- B3 (campaign plan): `QUALIFICATION_CAMPAIGN_PLAN.md`

---

## 1. Review Process

### Trigger
Review begins after a qualification campaign (B3-style) has completed **all three sessions**: Asian, London, New York. Partial runs (e.g. single session) may be reviewed as a **preliminary** report but cannot reach a qualification verdict.

### Prerequisites

| Check | Pass condition |
|-------|----------------|
| Campaign results exist | `shadow_results/pepperstone_campaign_{ts}.json` readable |
| Gate passed | `MarketGateResult.passed == True` (B1 counterexample: gate ran during closure — invalid) |
| Ledger sealed | `SealedLedger.verify() == True`, hash chain intact |
| Reconcile report exists | `shadow_results/reconcile_{session}_{ts}.json` for each session |
| All 3 sessions present | Asian + London + NY result files available |
| No closure distortion | Session field != "closed" (B1 counterexample: Asian closure produced 18.5% acceptance driven by NO_CANONICAL_TICKS, not signal quality) |

### Input files

| File | Source | Format |
|------|--------|--------|
| Campaign results x3 | `shadow_results/pepperstone_campaign_{ts}_asian.json` | JSON: `{campaign_meta, ledger_entries, stats, rejections}` |
| Campaign results x1 | `shadow_results/pepperstone_campaign_{ts}_london.json` | Same schema |
| Campaign results x1 | `shadow_results/pepperstone_campaign_{ts}_ny.json` | Same schema |
| Reconcile reports x3 | `shadow_results/reconcile_asian_{ts}.json` | JSON: `{ledger_valid, orphan_positions, orphan_orders, ...}` |
| Gate check log | Extracted from campaign results `gate_log` | Raw `MarketGateResult` |

---

## 2. Review Metrics — Definitions and Formulas

### 2.1 Acceptance rate

```
acceptance_rate = total_accepted / total_signals
```

Per-session: `acceptance_rate_{session}`. Cross-session mean ± std.

B1 baseline (closure, invalid for comparison): 18.5%.

### 2.2 Rejection breakdown

Compute for each rejection reason code:

```
rejection_pct_{reason} = count_{reason} / total_rejections
rejection_pct_all = sum(rejection_pct_{reason})  # must equal 1.0
```

Known reason codes (from market gate and pipeline):

| Reason code | Source | Meaning |
|-------------|--------|---------|
| `NO_TICKS` / `NO_CANONICAL_TICKS` | Pipeline tick gate | Zero canonical ticks at cycle |
| `SPREAD_TOO_WIDE` | `SpreadShockGate` or market gate | Spread exceeds threshold |
| `GEOMETRY_FAIL` | `validate_signal_geometry()` | SL/TP geometry constraint violation |
| `DUPLICATE` | `SignalDeduplicator` | Signal fingerprint already seen |
| `EVENT_RISK_BLOCKED` | Event calendar gate | High-impact news window |
| `GATE_FAILED` | `check_market_open()` | Pre-flight gate rejected (should not happen mid-campaign) |

### 2.3 Spread distribution

At acceptance time, collect spread values:

```
spread_mean = mean(accepted_spreads)
spread_median = median(accepted_spreads)
spread_std = std(accepted_spreads)
spread_p50, spread_p95, spread_p99 = percentiles(accepted_spreads)
```

Per-session comparison required — spread profiles differ materially across Asian (thin), London (liquid), NY (volatile). B1 counterexample: closure spread 0.22–0.31 pip range was static/fallback, not representative.

### 2.4 Slippage distribution

```
slippage_i = fill_price_i - signal_price_i
slippage_mean = mean(slippages)
slippage_std = std(slippages)
```

Report: mean ± 1σ, mean ± 2σ coverage. Flag if mean deviates from zero beyond expected spread cost.

### 2.5 Cost breakdown

| Component | Formula | Notes |
|-----------|---------|-------|
| Total cost | `sum(entry_spread + commission_per_lot)` | From ledger |
| Cost per accepted | `total_cost / total_accepted` | Per-signal avg cost |
| Spread cost | `sum(entry_spread)` | Aggregate spread paid |
| Commission | `sum(commission_per_lot)` | Aggregate broker commission |
| Cost per session | `total_cost_{session}` | Session-level decomposition |

### 2.6 No-tick rate

```
no_tick_rate = no_tick_rejections / total_rejections
```

High no-tick rate suggests session-level liquidity issues or data feed gaps. B1: 100% NO_CANONICAL_TICKS (closure). Qualification expectation: < 5%.

### 2.7 Session coverage

| Metric | Formula |
|--------|---------|
| Session hours | `last_timestamp - first_timestamp` per session (UTC) |
| Signals per session | `total_signals_{session}` |
| Signal density | `total_signals / hours` per session |
| Missing hours | Expected session hours - actual hours (abnormal if > 0) |

Expected hours: Asian 9h, London 9h, NY 9h (with overlaps 08-09 Asian/London, 13-17 London/NY).

### 2.8 Market-open coverage

Fraction of each session where gate `check_market_open() == passed`:

```
market_open_coverage = cycles_with_gate_passed / total_cycles
```

Expected: 1.0 (gate should always pass mid-session if pre-flight passed). If < 1.0, flag session for gate instability.

### 2.9 Reconciliation errors

| Error type | Check method | Tolerance |
|------------|-------------|-----------|
| Open positions | `mt5.positions_get(symbol)` | Count == 0 |
| Pending orders | `mt5.orders_get(symbol)` | Count == 0 |
| Ledger hash breaks | `SealedLedger.verify()` | 0 breaks |
| Signal count mismatch | `total_signals == accepted + rejected` | Exact match |
| Entry index gaps | Check `entry_index` sequence | No gaps |

Report per session and consolidated.

---

## 3. Review Report Format

> Instructions: Copy the section below into a new file under `docs/reviews/QUALIFICATION_REVIEW_YYYY-MM-DD.md`. Replace `__` placeholders with computed values. Remove sections marked _[if N/A]_.

---

### 3.1 Campaign Meta

| Field | Value |
|-------|-------|
| **Review date** | YYYY-MM-DD |
| **Campaign date(s)** | YYYY-MM-DD |
| **Sessions covered** | Asian / London / NY / _(list actual)_ |
| **Symbol** | XAUUSD |
| **Gate status at start** | PASS / FAIL |
| **Gate status at end** | PASS / FAIL |
| **DRY_RUN_MODE** | True / False |
| **Results files** | `shadow_results/pepperstone_campaign_*.json` (x__) |
| **Reconcile files** | `shadow_results/reconcile_*.json` (x__) |
| **Reviewer** | |

---

### 3.2 Summary Statistics

| Metric | Asian | London | NY | Consolidated |
|--------|-------|--------|----|-------------|
| Total signals | __ | __ | __ | __ |
| Accepted | __ | __ | __ | __ |
| Rejected | __ | __ | __ | __ |
| Acceptance rate | __% | __% | __% | __% |
| No-tick rate | __% | __% | __% | __% |
| Total cost | __ | __ | __ | __ |
| Cost per accepted | __ | __ | __ | __ |
| Market-open coverage | __% | __% | __% | __% |

---

### 3.3 Acceptance Analysis

**Consolidated acceptance rate:** __.__%

Per-session delta:

| Session | Rate | vs Consolidated | vs B1 (18.5%) |
|---------|------|----------------|---------------|
| Asian | __% | ±__pp | ±__pp |
| London | __% | ±__pp | ±__pp |
| New York | __% | ±__pp | ±__pp |

> ⚠️ Flag if any session deviates > 5pp from consolidated mean — indicates session-dependent gate behaviour.

Cross-session acceptance mean: __.__%
Cross-session acceptance std:  __.__%

---

### 3.4 Rejection Analysis

| Reason | Asian | London | NY | Total | % of all rejections |
|--------|-------|--------|----|-------|-------------------|
| NO_TICKS | __ | __ | __ | __ | __% |
| SPREAD_TOO_WIDE | __ | __ | __ | __ | __% |
| GEOMETRY_FAIL | __ | __ | __ | __ | __% |
| DUPLICATE | __ | __ | __ | __ | __% |
| EVENT_RISK_BLOCKED | __ | __ | __ | __ | __% |
| GATE_FAILED | __ | __ | __ | __ | __% |
| _(other)_ | __ | __ | __ | __ | __% |

**Total rejections:** __  (must equal sum of all reasons)

Dominant rejection reason: __  (__%)

Compare with B1: B1 had 100% NO_CANONICAL_TICKS (closure artefact). In a live qualification campaign, NO_TICKS should be < 5%.

---

### 3.5 Spread and Slippage Analysis

**Spread at acceptance time:**

| Statistic | Asian | London | NY | Consolidated |
|-----------|-------|--------|----|-------------|
| Mean | __ pips | __ pips | __ pips | __ pips |
| Median | __ pips | __ pips | __ pips | __ pips |
| Std | __ pips | __ pips | __ pips | __ pips |
| p50 | __ pips | __ pips | __ pips | __ pips |
| p95 | __ pips | __ pips | __ pips | __ pips |
| p99 | __ pips | __ pips | __ pips | __ pips |

**Slippage (fill_price - signal_price):**

| Statistic | Asian | London | NY | Consolidated |
|-----------|-------|--------|----|-------------|
| Mean | __ | __ | __ | __ |
| Std | __ | __ | __ | __ |
| Mean - 1σ | __ | __ | __ | __ |
| Mean + 1σ | __ | __ | __ | __ |
| % within 1σ | __% | __% | __% | __% |

> ⚠️ If slippage mean > 0.5 pips in any session, flag for execution quality review.

---

### 3.6 Cost Analysis

| Component | Asian | London | NY | Consolidated |
|-----------|-------|--------|----|-------------|
| Total cost | __ | __ | __ | __ |
| Spread cost | __ | __ | __ | __ |
| Commission | __ | __ | __ | __ |
| Cost per accepted | __ | __ | __ | __ |
| Cost per signal (all) | __ | __ | __ | __ |

Cost breakdown by component:

| Component | Amount | % of total |
|-----------|--------|-----------|
| Spread cost | __ | __% |
| Commission | __ | __% |

---

### 3.7 Session Coverage

| Session | Expected hours | Actual hours | Signals | Signal density (signals/h) |
|---------|---------------|-------------|---------|--------------------------|
| Asian | 9.0 | __ | __ | __ |
| London | 9.0 | __ | __ | __ |
| New York | 9.0 | __ | __ | __ |

Session overlap periods:

| Overlap | Hours (UTC) | Both sessions active |
|---------|-------------|---------------------|
| Asian + London | 08:00–09:00 | Yes / No _(if no, flag)_ |
| London + NY | 13:00–17:00 | Yes / No _(if no, flag)_ |

> ⚠️ Flag if actual hours < expected hours by > 5 minutes — possible premature stop.

---

### 3.8 Reconciliation Check

| Check | Asian | London | NY | Consolidated |
|-------|-------|--------|----|-------------|
| Ledger valid | Y/N | Y/N | Y/N | Y/N |
| Orphan positions | __ | __ | __ | __ |
| Orphan orders | __ | __ | __ | __ |
| Hash chain breaks | __ | __ | __ | __ |
| Signal count match | Y/N | Y/N | Y/N | Y/N |
| Entry index gaps | Y/N | Y/N | Y/N | Y/N |
| Timestamps UTC-monotonic | Y/N | Y/N | Y/N | Y/N |

**Consolidated reconcile result:** PASS / FAIL

> FAIL requires investigation before qualification verdict can be entered. Do not proceed to Section 3.9 until all FAIL items are resolved.

---

### 3.9 Qualification Verdict

Select one:

| Verdict | Condition |
|---------|-----------|
| **VALID** | All sessions passed, all metrics within expected bounds, reconcile PASS, no closure distortion |
| **VALID_WITH_CAVEATS** | Minor anomalies (e.g. one session acceptance > 5pp from mean, spread p95 above threshold, single reconcile warning). Caveats listed below. |
| **INVALID** | Any session failed gate, reconcile FAIL, data integrity errors, or closure/market-closed contamination |

**Verdict:** __

**Caveats (if VALID_WITH_CAVEATS):**
1. __
2. __

**Supporting rationale:**
__

**Reviewer signature:** __
**Date:** YYYY-MM-DD

---

## 4. Interpretation Rules (from B1)

### Valid for qualification inference

| Metric | Constraint |
|--------|-----------|
| **Acceptance rate** | Per-session comparison valid; consolidated rate is primary qualification signal |
| **Rejection distribution** | Valid — tells you which market conditions the strategy filters on |
| **Spread profile** | Valid — p50/p95/p99 across three sessions defines the strategy's operating range |
| **No-tick rate** | Valid — indicates data feed reliability per session |
| **Session coverage** | Valid — confirms the campaign exercised all intended market windows |
| **Market-open coverage** | Valid — measures gate stability throughout the session |
| **Reconciliation errors** | Valid — zero-tolerance; any error invalidates the campaign |

### NOT valid for qualification inference

| Metric | Why |
|--------|-----|
| **PnL** | Hypothetical only — fill model is simulated, not live execution. B1 counterexample: -39.32 closure PnL was meaningless. |
| **Expectancy** | Requires live slippage model and execution latency distribution — qualification data does not provide these. |
| **Win-rate** | Not computable from qualification data. Qualification tests market access, not strategy edge. |
| **Signal quality (individual)** | Individual signal quality is confounded by gate rejections. Aggregate patterns (acceptance rate, spread profile) are valid but per-signal quality is not. |
| **Slippage (absolute)** | Slippage distribution is indicative but absolute values depend on the fill model's assumptions. Compare across sessions for relative differences only. |

### Cross-reference: B1 counterexamples

| B1 observation | Why it is not qualification evidence | B4 treatment |
|----------------|--------------------------------------|-------------|
| 18.5% acceptance rate | Closure — tick absence drove rejections, not signal logic | B4 acceptance rate baseline is live-session only |
| 0.22–0.31 pip spread range | Static/fallback spread during closure | B4 expects session-varying spreads (wider Asian, tighter London) |
| 100% NO_CANONICAL_TICKS | No market data during closure | B4 expects < 5% no-tick rate |
| -39.32 hypothetical PnL | Not derived from executable prices | B4 ignores PnL entirely |
| "All infrastructure nominal" | True for plumbing, irrelevant for qualification | B4 reconciles plumbing check + adds strategy-facing metrics |

---

## 5. File References

| Module | Path | Role |
|--------|------|------|
| `MarketGateResult` | `execution/qualification/market_gate.py:13` | Gate result dataclass — source of gate status |
| `check_market_open()` | `execution/qualification/market_gate.py:42` | Pre-flight gate |
| `ReconciliationResult` | `canary/position_reconciler.py:6` | Position reconciliation result |
| `reconcile_positions()` | `canary/position_reconciler.py:14` | Broker vs ledger check |
| B3 Campaign Plan | `docs/campaigns/QUALIFICATION_CAMPAIGN_PLAN.md` | Campaign design, pre-flight checks, collection schema |
| B1 Closure Campaign | `docs/campaigns/CLOSURE_PERIOD_CAMPAIGN_20260624.md` | Counterexample — closure distortion reference |
