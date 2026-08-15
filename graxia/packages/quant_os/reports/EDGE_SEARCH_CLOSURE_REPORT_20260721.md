# EDGE SEARCH CLOSURE REPORT

**Date:** 2026-07-21 | **Status:** FORMAL CLOSURE
**Evidence Base:** 40+ trials, verified + unverified engines

---

## Executive Summary

After exhaustive testing of ~38 distinct strategy variants across ALL major strategy classes and asset classes, **no tradeable edge exists in directional strategies**. Grid strategy backtest has bugs and needs fixing before proper evaluation.

**Key Correction:** Previous summaries inflated "1,021 trial-slots" to imply 1,021 independent tests. The actual number of distinct strategy variants tested is ~38. The 1,021 number is for multiple-testing correction (DSR), not strategy count.

---

## Trial Count — Corrected

| Category | Trial-Slots | Distinct Strategies | Status |
|----------|-------------|---------------------|--------|
| Bulk parameter sweep (1-1000) | 1,000 | ~6 base types | ALL REJECTED |
| Individual hypotheses (1001-1008) | 8 | 8 | ALL REJECTED |
| ICT batch (1009-1021) | 13 | 13 | ALL REJECTED |
| Direction B (3001-3008) | 8 | 8 | ALL REJECTED |
| Pooled D1 strategies | — | 17 | ALL REJECTED |
| Cross-sectional | — | 1 | ⚠️ UNTRUSTWORTHY |
| Untested strategies | — | 5 | ALL REJECTED |
| Grid | — | 1 | ⚠️ BUGGY BACKTEST |
| **TOTAL** | **1,029 slots** | **~39 distinct** | |

---

## Strategy Classes — Final Verdict

### ❌ ALL REJECTED — Directional Strategies

| Class | Strategies | Best dk_t | Verdict |
|-------|-----------|-----------|---------|
| RSI Mean Reversion | 3 variants | -0.22 | REJECT |
| Momentum 12M | 2 variants | -0.39 | REJECT |
| Hybrid Mom MR | 2 variants | -0.41 | REJECT |
| Donchian Breakout | 4 variants | -0.53 | REJECT |
| Bollinger Squeeze | 1 | -0.60 | REJECT |
| Liquidity Sweep | 1 | -0.52 | REJECT |
| Volume Breakout | 2 variants | -0.49 | REJECT |
| Carry Trade | 1 | -0.98 | REJECT |
| Vol Risk Premium | 1 | -1.10 | REJECT |
| Cross-Asset Momentum | 1 | +0.06 | REJECT |
| DXY Divergence | 1 | -1.43 | REJECT |
| COT Positioning | 1 | -0.12 | REJECT |
| FOMC Drift | 1 | -0.83 | REJECT |
| Funding Rate Arb | 1 | 0.0 | REJECT |
| ETH Vol Confirm | 1 | -1.35 | REJECT |
| BTC-ETH Vol Spread | 1 | 0.0 | INSUFFICIENT_DATA |

### ⚠️ UNTRUSTWORTHY — Cross-Sectional Momentum

| Metric | Value | Issue |
|--------|-------|-------|
| dk_t | -2.1255 | Produced by standalone script, NOT verified engine |
| Engine | Standalone | Bypasses BacktestEngine, ExecutionSimulator, InlineContractSpec |
| Bugs | Commission dropped for indices | NAS100, US30 get zero commission |
| Status | UNTRUSTWORTHY | Needs re-run through verified engine |

### ⚠️ BUGGY — Grid Strategy (First-Ever Test)

| Metric | Value | Issue |
|--------|-------|-------|
| dk_t | -49.2051 | Absurdly negative — backtest bug |
| XAUUSD | trades=0, return=-40,598 | No trades but massive loss — bug |
| NAS100 | return=-5,562,002 | Absurd — grid not designed for indices |
| Status | BUGGY | Backtest needs fixing before evaluation |

**Grid backtest issues:**
- XAUUSD/XAGUSD: 0 trades but massive losses → equity curve bug
- NAS100/US30: Absurd returns → grid_step calculation wrong for indices
- All assets: max_dd=0.0 → unrealized P&L not tracked correctly

---

## Cross-Sectional Audit

**Script:** `scripts/edge_search_cross_sectional.py`
**Engine:** Standalone (NOT `backtest/engine.py`)
**Verdict:** UNTRUSTWORTHY

The script bypasses the verified BacktestEngine and uses naive `pct_change × signal` logic. This means:
- No proper fill model (SL/TP not enforced)
- No contract spec (pip values hardcoded)
- No position sizing (raw returns, not risk-weighted)
- Commission dropped for indices

**Action Required:** Re-run through BacktestEngine before any conclusion.

---

## Grid Strategy Assessment

Grid is fundamentally different from all38 rejected strategies:
- **Mechanism:** Profits from price oscillation between grid levels
- **NOT directional:** Does not forecast price direction
- **First-ever test:** Never been through DK-test before
- **Backtest bugs:** Current results are absurd and untrustworthy

**Action Required:** Fix Grid backtest bugs, then re-run DK-test.

---

## Recommendations

1. **Accept NO EDGE for directional strategies** — evidence is overwhelming
2. **Fix Grid backtest bugs** — current results are absurd
3. **Re-run cross-sectional through verified engine** — current result is untrustworthy
4. **After fixes, re-evaluate Grid** — only remaining untested mechanism

---

## Evidence Index

| File | Content |
|------|---------|
| `reports/edge_search_all_results_corrected_v2.json` | 17 directional strategies |
| `reports/edge_search_path_b_dk_test.json` | 4 macro strategies |
| `reports/edge_search_untested_20260720.json` | 5 event/crypto strategies |
| `reports/edge_search_cross_sectional_20260720.json` | Cross-sectional (untrustworthy) |
| `reports/edge_search_grid_20260721.json` | Grid (buggy) |
| `reports/trial_count_reconciliation_20260720.json` | Trial count audit |
| `research/hypothesis_registry.json` | All trials registered |
| `research/trial_ledger.json` | Direction A ledger |
| `research/trial_ledger_b.json` | Direction B ledger |

---

**Generated:** 2026-07-21
**Next Action:** Fix Grid backtest bugs + re-run cross-sectional through verified engine
