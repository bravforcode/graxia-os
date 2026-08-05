# DATA_INTEGRITY_CROSS_VALIDATION.md — Phase 2

## 2.1 — Bad Tick / Price Spike Detection

- **Filter exists**: `ticks/data_quality.py` has `TickQualityChecker` with checks for: negative bid/ask, inverted spread, extreme spread
- **Code location**: `ticks/data_quality.py` (imported but not wired into live path — **ORPHANED**)
- **Manual scan**: Not performed. No evidence of historical outlier detection.
- **Verdict**: Filter exists in ticks/ module but is not integrated into the data pipeline or backtest. **[UNVERIFIED — filter never exercised on historical data]**

## 2.2 — Independent Reference Feed Comparison

**NEVER PERFORMED.** No comparison against Dukascopy, HistData, TrueFX, or another broker's feed exists in the codebase.

The entire backtest rests on the unverified assumption that Pepperstone's historical feed is accurate. This matters because Pepperstone is a market-maker/dealing-desk broker for some instruments — such brokers have been documented constructing their own historical price feeds.

**Severity**: P2 — does not block paper trading but means data quality is unverified.

## 2.3 — Gap & Missing-Bar Forensics

No systematic gap quantification exists. `backtest/data_loader.py` has basic gap-filling but does not report gap percentage. `data/mt5_tick_ingester.py` tracks tick-level gaps but not bar-level.

**[QUANTIFIED GAP ANALYSIS NOT PERFORMED]**

## 2.4 — Vendor/Source Changeover Detection

No evidence of source changeover detection. If the broker server changed during the backtest period, there is no mechanism to detect a discontinuity.

**[NEVER PERFORMED]**

## 2.5 — Per-Asset-Class Feed Reliability

| Asset Class | Bad-Tick Filter Validated? | Independent Comparison? | Verdict |
|---|---|---|---|
| FX majors | No (ticks/data_quality.py exists but unwired) | No | **[UNVERIFIED]** |
| Metals | No | No | **[UNVERIFIED]** |
| Crypto | No | No | **[UNVERIFIED]** |
| Indices | No | No | **[UNVERIFIED]** |

Feed quality checks that passed for EURUSD do NOT transfer to XPDUSD or BTCUSD without independent verification (R22).

**P0 Findings**: 0
**P1 Findings**: 0
**P2 Findings**: 1 (no independent feed validation)
**P3 Findings**: 3 (no gap analysis, no changeover detection, no per-asset-class validation)
