# B3 — Qualification Campaign Plan

**Track:** B3 (Qualification)
**Symbol:** XAUUSD
**Broker:** Pepperstone-Demo
**Sessions:** Asian, London, New York (no closure contamination)
**Gate module:** `execution/qualification/market_gate.py`
**Runner base:** `shadow/pepperstone_campaign.py`
**Previous campaign:** `CLOSURE_PERIOD_CAMPAIGN_20260624.md` (B1 — closure period, infra-only)

---

## 1. Pre-flight checks

Every campaign start MUST call `check_market_open()` from `market_gate.py`:

| Check | Fail action |
|-------|-------------|
| Session not "closed" | Abort — not a valid qualification window |
| Plan not expired | Abort if `plan_expiry` passed |
| Terminal connected | Abort |
| Symbol open for trade | Abort |
| Spread ≤ 50.0 cap | Abort — excessive during thin liquidity |
| Tick fresh (≤ 60s) | Abort — stale data = fake signals |
| No positions on symbol | Abort — orphan state |
| No pending orders | Abort — orphan state |
| DRY_RUN_MODE gate | If True, gate passes with simulated OK |

If gate fails → campaign does NOT start. Log reason, exit cleanly, reject any downstream signal processing.

### Expected session schedule (UTC)

| Session | Hours (UTC) | Qualification eligibility |
|---------|-------------|--------------------------|
| Asian   | 00:00–09:00 | Valid |
| London  | 08:00–17:00 | Valid (overlap with Asian 08-09, NY 13-17) |
| New York| 13:00–22:00 | Valid |
| Closed  | 22:00–00:00 | Not valid — abort |

---

## 2. Campaign parameters

| Parameter | Value | Rationale |
|-----------|-------|-----------|
| Symbol | XAUUSD | Same as B1 for comparable rejection baseline |
| DRY_RUN_MODE | `True` first cycle | Zero market risk, gate validates without live MT5 |
| Duration | 9+ hours (one full session) | Minimum — Asian 00-09, London 08-17, NY 13-22 |
| Interval | 60s | Same as `pepperstone_campaign.py` — 1 cycle/minute |
| Spread cap | 50.0 pips | Same as `check_market_open()` default |
| Tick max age | 60s | Same as gate default |
| Strategy version | `pepperstone_v1` | Same as B1 — consistent signal framework |
| Feature hash | `pepperstone_p85` | Same as B1 — consistent dedup scope |
| SL/TP geometry | 10× spread SL, 20× spread TP | Same as `pepperstone_campaign.py` default |

### Session targeting

One campaign = one full session. To cover all three:
- **Pass 1:** Asian session (start 00:00 UTC)
- **Pass 2:** London session (start 08:00 UTC)
- **Pass 3:** NY session (start 13:00 UTC)

Each pass is independent, has its own `shadow_results/` file, its own ledger, its own reconcile report.

---

## 3. Data collection

### Per-cycle record (1 cycle/minute)

| Field | Source | Purpose |
|-------|--------|---------|
| `outcome` | Gate pipeline | `accepted` / `rejected_*` |
| `rejection_reason` | Gate pipeline | Categorical reason string |
| `spread` | MT5 tick (ask - bid) | Spread profile per session |
| `spread_p50/p95/p99` | `SpreadTracker.percentiles()` | Rolling distribution |
| `direction` | Signal generation | BUY/SELL |
| `entry_price`, `sl`, `tp` | Signal generator | Geometry validation input |
| `geometry_ok` | `validate_signal_geometry()` | Pass/fail with reason |
| `spread_shock` | `SpreadShockGate.is_shock()` | Shock flag |
| `dedup_duplicate` | `SignalDeduplicator.is_duplicate()` | Duplicate flag |
| `event_risk_state` | Event calendar gate | CLEAR / BLOCKED |
| `slippage` | Fill model (fill vs signal) | Hypothetical spread + slippage cost |
| `pnl_net` | `simulate_lifecycle()` | Hypothetical P&L (not for interpretation) |
| `ledger_entry_hash` | `SealedLedger` | Hash chain integrity |
| `no_tick_events` | `canonical_tick_count == 0` | Market data gap tracking |

### Ledger

Every signal → decision → outcome is recorded in `SealedLedger` (append-only SHA256 chain). Ledger entries include:

- `entry_index`: sequential
- `signal_id`: cycle identifier
- `previous_hash`: previous record hash
- `record_hash`: SHA256 of entry data
- `outcome`: accept or reject type
- `pnl_net`: hypothetical P&L
- `timestamp`: UTC ISO

Ledger verification: `SealedLedger.verify()` must return `True` at campaign end.

### Output file

Written to `shadow_results/pepperstone_campaign_{YYYYMMDD}_{HHMMSS}.json` — same structure as B1.

---

## 4. Post-campaign reconciliation

### 4.1 Broker state vs campaign ledger

| Check | Method | Pass condition |
|-------|--------|----------------|
| No open positions | `mt5.positions_get(symbol)` | Count == 0 |
| No pending orders | `mt5.orders_get(symbol)` | Count == 0 |
| Ledger valid | `SealedLedger.verify()` | `True` |
| Session seal | Campaign summary hash matches terminal state | No orphan records |

Use `canary/position_reconciler.py::reconcile_positions()` if expected positions exist.

### 4.2 Data integrity

- `total_signals` == `accepted + rejected`
- All `record_hash` values match SHA256 recomputation
- No gap in `entry_index` sequence
- Timestamps are UTC-monotonic

### 4.3 Reconcile report

Written alongside the campaign results file. Contents:

```
campaign: pepperstone_campaign_{ts}.json
session: asian|london|ny
ledger_valid: true/false
orphan_positions: 0/<count>
orphan_orders: 0/<count>
hash_chain_breaks: 0/<count>
signal_count_match: true/false
status: PASS/FAIL
```

---

## 5. Expected outputs

| Output | Path | Format |
|--------|------|--------|
| Campaign results | `shadow_results/pepperstone_campaign_{ts}.json` | JSON (same schema as B1) |
| Reconcile report | `shadow_results/reconcile_{session}_{ts}.json` | JSON |
| Ledger chain | Embedded in results file under `ledger_entries` | List of sealed records |

---

## 6. Execution constraints

1. **DRY_RUN_MODE=True for first cycle** — set `DRY_RUN_MODE = True` in `market_gate.py:7`. Gate passes without live MT5. After first cycle validates plumbing, flip to `False` for live MT5 check.
2. **One qualification pass per invocation** — campaign runs one session, stops. No automatic session chaining.
3. **No retry on uncertain** — if `check_market_open()` returns `passed=False` mid-campaign, campaign ends. Do not restart. Log the reason.
4. **Mid-session stop** — campaign can be stopped at any cycle boundary (`time.sleep` between cycles). Clean shutdown: `mt5.shutdown()`, seal ledger, write partial results.
5. **No order submission** — read-only MT5 (same as `MT5ReadOnly` in `pepperstone_campaign.py`). No `order_send`, no `position_close`.

---

## 7. Interpretation rules (from B1)

| Metric | Interpretable in B3? | Constraint |
|--------|---------------------|------------|
| Acceptance rate | **Yes** | Per-session comparison against B1 baseline (18.5%) |
| Rejection distribution | **Yes** | NO_CANONICAL_TICKS vs geometry vs spread_shock vs duplicate |
| Spread profile | **Yes** | p50/p95/p99 per session, compare across Asian/London/NY |
| PnL | **NO** | Hypothetical only — not live-valid |
| Expectancy | **NO** | Requires live execution and slippage model |
| Win-rate | **NO** | Not computable from qualification data |
| Signal quality | **NO** | Confounded by gate rejections — need live pass for signal eval |

### What B3 validly answers

- Does the gate pipeline behave differently across sessions? (acceptance rate delta)
- Which rejection reasons dominate each session? (session-specific market micro-structure)
- Is spread stable enough for qualification? (spread profile vs cap)

---

## 8. File references

| Module | Path | Role |
|--------|------|------|
| `MarketGateResult` | `execution/qualification/market_gate.py:13` | Gate result dataclass |
| `check_market_open()` | `execution/qualification/market_gate.py:42` | Pre-flight gate |
| `PepperstoneCampaignRunner` | `shadow/pepperstone_campaign.py:312` | Campaign runner base |
| `SealedLedger` | `shadow/pepperstone_campaign.py:154` | Append-only ledger |
| `ShadowPipeline` | `shadow/pipeline.py:316` | Gate pipeline |
| `SpreadShockGate` | `shadow/pipeline.py:235` | Spread shock detection |
| `SpreadTracker` | `shadow/pepperstone_campaign.py:96` | Spread percentiles |
| `reconcile_positions()` | `canary/position_reconciler.py:14` | Broker vs ledger check |
| `CLOSURE_PERIOD_CAMPAIGN_20260624.md` | `docs/campaigns/CLOSURE_PERIOD_CAMPAIGN_20260624.md` | B1 interpretation rules |
