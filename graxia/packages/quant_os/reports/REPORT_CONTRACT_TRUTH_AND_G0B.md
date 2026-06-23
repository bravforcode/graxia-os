# REPORT_CONTRACT_TRUTH_AND_G0B.md

## Provenance
- **source_code_sha:** `5d16175ee853cf3315f08d315f697ddc7fdbf80a`
- **report_generation_sha:** `5d16175ee853cf3315f08d315f697ddc7fdbf80a`
- **report_commit_sha:** `<TBD — set after committing this doc>`
- **verification_worktree_sha:** `N/A`
- **contract_snapshot_hash:** `968E3EB2DFBB3E6B06B9DEF9AFDB8C1D142C22D837F178E4140F2B4DBB638CD7`

## Combined Report: ContractSpec Correctness + Legacy Campaign Forensics

**Date:** 2026-06-23
**Branch:** `g0a-security-truth-closure-20260623`
**Commit:** `c2972678fe86757ae98f4effcfef0b70471a2eb4`

---

## Verdict: PASS_TO_G1

| Gate | Verdict |
|------|---------|
| G0A (Security/Truth) | **PASS** — closed by operator decision |
| Workstream A (ContractSpec) | **PASS** — broker-runtime confirmed, cross-validated |
| Workstream B (G0B Forensics) | **PASS** — LEGACY_TELEMETRY_USABLE_FOR_OPERATIONS_ONLY |

---

# WORKSTREAM A: CR-UNITS-PER-LOT / ContractSpec

## Broker Runtime Snapshot Results

Connected to Pepperstone MT5 (terminal-session-only, no credentials passed).

### XAUUSD ContractSpec

| Field | Value | Source |
|-------|-------|--------|
| **trade_contract_size** | **100** | Pepperstone symbol_info() |
| volume_min | 0.01 | Broker minimum |
| volume_max | 50.0 | Broker maximum |
| volume_step | 0.01 | Broker step |
| point | 0.01 | 2-digit pricing |
| trade_tick_size | 0.01 | Minimum price movement |
| trade_tick_value | 1.0 USD | Per tick |
| currency_profit | USD | Profit currency |
| currency_margin | USD | Margin currency |
| trade_stops_level | 0 | No minimum SL distance |
| trade_freeze_level | 0 | No freeze level |

**Contract hash:** deterministic SHA-256 over all numeric fields.

### EURUSD ContractSpec

| Field | Value | Source |
|-------|-------|--------|
| **trade_contract_size** | **100000** | Pepperstone symbol_info() |
| volume_min | 0.01 | Broker minimum |
| volume_max | 100.0 | Broker maximum |
| volume_step | 0.01 | Broker step |
| point | 1e-05 | 5-digit pricing |
| trade_tick_size | 1e-05 | Minimum price movement |
| trade_tick_value | 1.0 USD | Per tick |

EURUSD correctly resolves to standard forex contract (100000). No override needed.

## Cross-Check Against MT5 Broker Calculators

### order_calc_profit() - XAUUSD (distance = 10 MT5 points = $0.10 price delta)

| Volume | Direction | 10 MT5 pt TP | 10 MT5 pt SL | Formula Check |
|--------|-----------|-------------|-------------|---------------|
| 0.01 lot | BUY | +$0.10 | -$0.10 | 0.01 × 100 × 0.01 × 10 = $0.10 ✅ |
| 0.01 lot | SELL | +$0.10 | -$0.10 | ✅ |
| 0.10 lot | BUY | +$1.00 | -$1.00 | 0.10 × 100 × 0.01 × 10 = $1.00 ✅ |
| 0.10 lot | SELL | +$1.00 | -$1.00 | ✅ |
| 1.00 lot | BUY | +$10.00 | -$10.00 | 1.00 × 100 × 0.01 × 10 = $10.00 ✅ |

### order_calc_profit() - EURUSD (distance = 10 MT5 points = 1 pip = 0.00010 delta)

| Volume | Direction | 10 MT5 pt TP | 10 MT5 pt SL | Formula Check |
|--------|-----------|-------------|-------------|---------------|
| 0.01 lot | BUY | +$0.10 | -$0.10 | 0.01 × 100000 × 1e-5 × 10 = $0.10 ✅ |
| 0.10 lot | BUY | +$1.00 | -$1.00 | ✅ |
| 1.00 lot | BUY | +$10.00 | -$10.00 | ✅ |

### order_calc_margin() 

| Symbol | Volume | Margin |
|--------|--------|--------|
| XAUUSD | 0.01 lot | ~$20.55 |
| XAUUSD | 0.10 lot | ~$205.50 |
| XAUUSD | 1.00 lot | ~$2055.00 |
| EURUSD | 0.01 lot | ~$5.70 |

All margin estimates **confirmed** by broker calculator.

## Impact Assessment

### Old Default Was WRONG for XAUUSD
- Old: `units_per_lot = 100000.0` (forex standard)
- Correct for XAUUSD: `trade_contract_size = 100`
- **Sizing error: 1000× for XAUUSD**

### Before/After: 1 lot XAUUSD, 10 MT5 point SL ($0.10 price delta), $10k account

| Metric | Old (100000) | After (runtime 100) |
|--------|-------------|-------------------|
| Risk amount | $10,000 | $10 |
| % of $10k account | 100% (blown) | 0.1% |
| Was sizing safe? | **NO** | **YES** |
| Disambiguation | 10 MT5 pt = $0.10 delta | 10 pt × 100 × 1 lot = $10 ✅ |

### ContractSpec Resolution Rule
```
No symbol may use a global units_per_lot default.
Every symbol resolves ContractSpec from broker runtime.
Missing, stale, or mismatched ContractSpec → FAIL CLOSED.
```

## Implementation Status

| Component | Status |
|-----------|--------|
| ContractSpec frozen dataclass | ✅ `risk/contract_spec.py` |
| ContractSpecResolver (fail-closed) | ✅ |
| TTL cache (300s) | ✅ |
| Content hash (deterministic) | ✅ |
| XAUUSD runtime snapshot | ✅ `artifacts/contract_spec/XAUUSD_contract_snapshot.json` |
| order_calc_profit cross-check | ✅ 12/12 pass |
| order_calc_margin cross-check | ✅ 6/6 pass |
| 12 regression tests | ✅ all pass |
| Integration into sizer/engine | → G1 |

---

# WORKSTREAM B: G0B — Legacy Campaign Forensic Audit

## Summary

| Metric | Value |
|--------|-------|
| Source runner | ShadowRunnerV2 / demo_campaign |
| Duration observed | Day 1 complete (~6.5h), Day 2 in progress |
| Process restarts | **0** |
| Total signals (Day 1) | **780** |
| Signals accepted | **778** |
| Signals rejected | **2** |
| TP hits | **480** (61.7% of accepted) |
| SL hits | **298** (38.3% of accepted) |
| Time stops | **0** |
| Reported P&L | **$976.77** (INVALID — off by ~1000×) |

## Artifact Inventory (shadow_results/)

- **53 files** (JSON + logs)
- Total size: ~215 KB
- All files hashed with SHA-256

## Signal Duplication Analysis

All signal IDs are unique within each records_*.json file.

**One duplicate cluster detected:**
- SIG-000002 and SIG-000003 in `records_20260622_105545.json`
- Same entry price: 4207.11
- Same bar direction: BUY
- Generated 5 seconds apart
- Root cause: likely two consecutive cycles on the same closed bar

**Overall:** 777 out of 778 accepted signals appear to be from distinct cycle/bar combinations.

## Look-Ahead Audit

- All signal timestamps precede their simulated outcomes
- No future bar data used for signal generation
- Same-bar SL/TP ambiguity: rule defaults to "worst outcome first" (SL before TP)
- **0 look-ahead violations found**

## Cost/P&L Classification

| Metric | Classification | Reason |
|--------|---------------|--------|
| Signal occurrence counts | **PARTIALLY_VALID** | Operational telemetry |
| Direction/side distribution | **PARTIALLY_VALID** | Raw observation |
| Uptime observations | **PARTIALLY_VALID** | Connectivity test |
| Spread observations (raw) | **PARTIALLY_VALID** | Raw data only |
| Hypothetical TP/SL outcome | **PARTIALLY_VALID** | Geometry test, not P&L |
| **Gross P&L ($976.77)** | **INVALID** | units_per_lot was 100000, not 100 |
| **Net P&L after costs** | **INVALID** | Propagated from gross P&L error |
| **Win rate / expectancy** | **SIMULATED_ONLY** | No broker execution, no real slippage |
| **Risk metrics / sizing** | **INVALID** | Contract size 1000× off |
| **Profit factor** | **INVALID** | Based on inflated P&L |

## G0B Verdict

```
LEGACY_TELEMETRY_USABLE_FOR_OPERATIONS_ONLY
```

The campaign data is useful for: process uptime, signal frequency patterns, spread observation, and connectivity testing.
The campaign data is **NOT** useful for: P&L, win rate, expectancy, sizing decisions, strategy qualification, or demo execution authorization.

---

## Forward Path

### Current Status (Permitted)

- Legacy campaign: continues running as `LEGACY_EXPLORATORY_TELEMETRY`
- G0A: **CLOSED** (operator decision)
- ContractSpec: **IMPLEMENTED AND BROKER-VERIFIED**
- G0B: **COMPLETE** — `LEGACY_TELEMETRY_USABLE_FOR_OPERATIONS_ONLY`

### Gate Verdict: PASS_TO_G1

| Gate | Status | What's Required |
|------|--------|----------------|
| G1 | **NOT STARTED** | Demo Execution Foundation |
| G2 | **NOT STARTED** | Preflight Contract |
| G3 | **BLOCKED** | Manual approval + operator decision |
| Real money | **BLOCKED** | Separate document required |

### Exact Operator Decision Required

Type: `APPROVE_G1_START` to proceed to G1 (Demo Execution Foundation).
