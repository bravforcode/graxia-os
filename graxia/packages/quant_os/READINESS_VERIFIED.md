# LIVE TRADING READINESS — Verified Status

**Date**: 2026-07-18
**Status**: 🔴 NOT READY
**Last verified**: 2026-07-18 by cross-referencing hypothesis_registry.json, trial_ledger.json, AUDIT_INDEX.md, cost_calibration.json, and code inspection

---

## Executive Summary

**The system is NOT ready for live trading.** Two independent blockers:

1. **No instrument has proven edge.** All 8 hypothesis trials (1001-1008) are REJECTED with p-values ranging 0.244-0.968. None approach significance.
2. **Cost baseline is unreliable.** Three independent cost sources disagree by up to 33x. No source has sufficient data (7+ day multi-session measurement) to serve as Go/No-Go basis.

---

## Category A: Edge Status (BLOCKING)

### A1. Hypothesis Registry

| Trial | Name | Instrument | p-value | Verdict |
|-------|------|------------|---------|---------|
| 1001 | RYDC Arm A | XAUUSD | 0.968 | REJECTED |
| 1003 | Cross-Asset Momentum | XAUUSD | 0.598 | REJECTED |
| 1004 | Session Pattern | XAUUSD | 0.934 | REJECTED |
| 1005 | Macro Regime MR | XAUUSD | 0.244 | REJECTED |
| 1006 | Gold Silver Spread | XAUUSD | 0.505 | REJECTED |
| 1007 | BTC Vol Clustering | BTCUSD | 0.248 | REJECTED |
| 1008 | Cross Asset Vol Rank | BTCUSD | 0.610 | REJECTED |

**Source**: `research/hypothesis_registry.json` + `research/trial_ledger.json` (cross-verified, both show identical values)

**Trial budget**: 1005/1022 used, 17 remaining

### A2. Universe

8 assets (verified from `scripts/pooled_strategy_test.py` UNIVERSE constant):
- XAUUSD, XAGUSD, EURUSD, GBPUSD, USDJPY, NAS100, US30, BTCUSD

**Note**: The old unverified document claimed "15 instruments". This is not supported by any registry or code.

---

## Category B: Cost Baseline (BLOCKING)

### B1. Three Sources — None Reliable

| Source | XAUUSD spread | Method | Reliability |
|--------|--------------|--------|-------------|
| `config/cost_calibration.json` | 0.36 bps | 20-sample single snapshot (2026-07-03) | **Low** — snapshot biased to quiet session |
| `core/cost_model.py` METALS | 12.0 bps | "Calibrated June 2026" | **Unknown** — methodology undocumented |
| `scripts/pooled_strategy_test.py` | 4.25 bps | Hardcoded `SYMBOL_SPREAD_PIPS["XAUUSD"] = 100.0` | **Unknown** — source of constant undocumented |

### B2. Why This Matters

- Gold spread can range from ~$0.10 (liquid London/NY overlap) to $2.00+ (rollover/news/Asian off-hours)
- 20-sample snapshot captured during one session cannot represent true average cost
- No source has multi-session, multi-day data

### B3. Required Action

Run `scripts/measure_spread_continuous.py --duration-days 7` to collect real baseline:
```bash
python scripts/measure_spread_continuous.py --duration-days 7
```

Output will be in `data/spread_measurements/summary.json` with per-session statistics.

---

## Category C: Known Bugs

### C1. PBO Fallback (FIXED 2026-07-18)

**Bug**: `validation/pipeline/runner.py` returned `pbo_val = 0.5` when <2 strategy configs, making result indistinguishable from real PBO.

**Fix**: Now returns `success=False` with clear error message. Verified by syntax check.

### C2. Walk-Forward Price Assertions

**Bug**: `scripts/walk_forward.py` has hardcoded XAUUSD price range assertions (`min close > 1000`). Fails on EURUSD-scale instruments.

**Status**: Open

### C3. CSV Loader Silent Fail

**Bug**: `validation/pipeline/runner.py` `_load_csv` silently drops columns and malformed rows.

**Status**: Open — blocks any macro/alt-data hypothesis testing.

---

## Category D: Infrastructure Status

### D1. Audit Findings

8 P0 blockers from `reports/AUDIT_INDEX.md` (2026-06-29, has provenance):
1. SL/TP trigger uses bar midpoint, not high/low
2. Swap costs never applied in backtest
3. Kill switch silently resets on corrupt JSON
4. Canonical pre-trade gate not wired to live orders
5. Crash recovery not wired
6. 3 API keys hardcoded in src
7. MT5 account num in git history
8. Real FRED key in `.env.example`

**Note**: The old unverified document claimed "47 Critical + 31 High findings". This is not supported by the actual audit document.

### D2. Paper Trading

0/60 required days completed. 0/100 required trades executed. Golden Rule #3 not met.

### D3. MT5 Gateway

Claim: "read-only stub" — **Unverified**. Originated from same source as other failed claims (LIVE_TRADING_READINESS_MASTER.md). Requires separate verification.

---

## Category E: Live Trading Verdict

| Criterion | Status | Notes |
|-----------|--------|-------|
| Proven edge | 🔴 NOT PROVEN | All 8 trials REJECTED |
| Cost baseline | 🔴 UNREliable | 3 sources disagree, no multi-day data |
| Paper trading | 🔴 NOT STARTED | 0/60 days |
| PBO gate | 🟡 FIXED | Fallback bug resolved 2026-07-18 |
| Audit blockers | 🟡 8 P0 | From verified source |
| MT5 gateway | ❓ UNVERIFIED | Requires separate trace |

**Recommendation**: NOT READY for live or paper trading. Begin with spread measurement (7+ days), then reassess.

---

## Appendix: Documents Referenced

| Document | Status | Used for |
|----------|--------|----------|
| `research/hypothesis_registry.json` | ✅ Verified | Trial outcomes |
| `research/trial_ledger.json` | ✅ Verified | Trial budget, cross-check |
| `reports/AUDIT_INDEX.md` | ✅ Verified | P0 blockers |
| `config/cost_calibration.json` | ⚠️ Partial | Cost data (20 samples) |
| `scripts/pooled_strategy_test.py` | ✅ Verified | Universe, cost constants |
| `LIVE_TRADING_READINESS_MASTER.md` | ❌ Untracked, 0/6 verified | NOT USED in this document |
