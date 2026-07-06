# DATA INTEGRITY & CROSS-VALIDATION — Phase 2
## Deep Audit v4.0 | 2026-07-05

---

### 2.1 Bad Tick / Price Spike Detection

#### 2.1.1 Filter for Erroneous Prices
- **Grep for outlier/mad/spike/outlier**: No price outlier detection found in any production data pipeline module.
- `backtest/data_loader.py:63`: Basic sanity check `o <= 0 or h <= 0 or lo <= 0 or c <= 0 or h < lo` — rejects negative prices and inverted high/low only. Does NOT detect:
  - Single-bar spike of 50+ pips reverting immediately
  - Bid/ask flip errors
  - Stale price that hasn't updated in N minutes
- `ticks/test_data_quality.py`: Has `check_tick()` that validates bid>0, ask>0, bid<ask — but this is in the TICK test module, not the BAR pipeline.

**Verdict**: FAIL — No spike/reversal detection in OHLCV bar ingestion. 50-pip single-bar outliers pass through unmolested.

#### 2.1.2 Manual Outlier Scanning
- **No evidence** of systematic manual outlier scanning. No outlier report files in `reports/`, `artifacts/`, or `Meta/`.
- The `data_pipeline/` directory contains config and auto_run but no quality assurance module.

---

### 2.2 Independent Reference Feed Comparison

#### 2.2.1 Reference Feed Audit
- Searched for `Meta/verified_sources_report.md`, `Meta/honest_web_research_report.md`, `Meta/broker_verification_report.md` — **NOT FOUND** in the repository tree.
- **No evidence** of feed comparison:
  - MT5 broker data vs Dukascopy historical
  - MT5 broker data vs HistData
  - MT5 broker data vs another broker (e.g., Pepperstone vs ICMarkets)
  - Crypto (ccxt/Binance) vs alternative exchange
- The `shadow/` directory contains time_source_reconciler.py (`shadow/time_source_reconciler.py:6`: "NO hardcode offsets. NO latency calculation. NO session/event decisions") — this is a time reconciliation tool, NOT a price feed comparison tool.

**Verdict**: FAIL — Zero independent reference feed comparison conducted. All price data is single-source (MT5 for forex/metals/indices, Binance for crypto).

---

### 2.3 Gap & Missing-Bar Forensics

#### 2.3.1 Quantification
- **No gap quantification code exists**. The word "gap" in the codebase refers to price gaps in FVG context (`core/smc_detectors.py` — Fair Value Gaps), not missing bar gaps in the time series.
- `data/pipeline.py` contains stub methods (`fetch_ohlcv`, `fetch_tick_data` both marked `# Placeholder impl` at :66, :72). No gap analysis.
- `scripts/build_features.py:265` drops NaN rows: `features = features.dropna()`. This silently removes any gap-induced NaN without reporting count or location.
- **Surrogate estimate**: `BARS_PER_YEAR` table at `backtest/metrics.py:23-30` defines expected bar counts. With `24_192` bars/year for M15 metals, a simple count check would reveal missing bars, but **this check is never performed**.

**Verdict**: FAIL — No gap quantification. Cannot determine what % of expected bars are missing or whether gaps cluster in specific periods (weekends, holidays, broker maintenance windows).

---

### 2.4 Vendor/Source Changeover Detection

#### 2.4.1 Data Source Consistency
- **Single MT5 connection** is assumed throughout. `data/feed.py:MT5DataFeed` initializes with `mt5.initialize()` using default terminal config.
- No mechanism to detect:
  - Broker change
  - MT5 server migration
  - Symbol specification change (spread, tick value, contract size)
- `broker/contract_spec.py:23` states "Source of truth: MT5 symbol_info(). Never hardcode." — but this is aspirational; the inline spec in `backtest/engine.py:InlineContractSpec` **does** hardcode for 9 symbols.

#### 2.4.2 Discontinuity Check
- **NONE**. No spread change detection, no price discontinuity check, no logic to compare "before" and "after" data periods.

**Verdict**: FAIL — No vendor/source changeover detection. Silent data contamination possible if broker/server/symbol config changes.

---

### 2.5 Per-Asset-Class Feed Reliability

#### 2.5.1 Instruments Audited

| Asset Class | Symbols | Data Source | Feed Reliability | Notes |
|-------------|---------|-------------|-------------------|-------|
| **Forex** | EURUSD, GBPUSD, USDJPY, AUDUSD, USDCAD, USDCHF, NZDUSD | MT5 `copy_rates_from_pos` | UNVERIFIED | 5-digit pricing via MT5. No cross-broker verification. |
| **Metals** | XAUUSD, XAGUSD, XPDUSD, XPTUSD | MT5 `copy_rates_from_pos` | UNVERIFIED | Spread varies by broker. XPDUSD/XPTUSD may have ~48-hour weekend gaps. |
| **Indices** | NAS100, US30 | MT5 `copy_rates_from_pos` | UNVERIFIED | CFD pricing. Only 16,128 bars/year (limited session). Weekend gaps expected. |
| **Crypto** | BTCUSD, ETHUSD | ccxt (Binance) `fetch_ohlcv()` | UNVERIFIED | 35,040 bars/year (24/7). Ccxt timestamps are UTC (correct). |

#### 2.5.2 Independent Verification Per Class
- **Forex**: No independent feed comparison. No ECN/STP broker data source for verification.
- **Metals**: XAUUSD is the primary traded symbol. Data verified only against MT5 broker — no LBMA fix or alternative source.
- **Indices**: CFD pricing from MT5. No comparison against futures (ES, NQ) or spot indices.
- **Crypto**: Single exchange (Binance). No comparison against Kraken, Coinbase, or Bybit for price consistency.

#### 2.5.3 Data Completeness
- `BARS_PER_YEAR` at `backtest/metrics.py:23-30` provides expected counts:
  - Crypto M15: 35,040 bars/year (24/7/365)
  - Metals M15: 24,192 bars/year
  - Forex M15: 24,192 bars/year
  - Indices M15: 16,128 bars/year
- These numbers are used for Sharpe annualization only. NO actual bar-count completeness check against them.

**Verdict**: FAIL — No per-asset-class feed reliability assessment. All instruments use single-source data with no verification.

---

### 2.6 Data Quality Assurance Module

#### 2.6.1 Tick-Level Quality
- `ticks/test_data_quality.py`: Has `check_tick()` with bid>0, ask>0, bid<ask checks. But test module — not wired to live pipeline.
- `ticks/test_tick_schema.py`: Validates tick format. Test module only.

#### 2.6.2 Bar-Level Quality
- `backtest/data_loader.py:62-64`: Validates `o>0, h>0, lo>0, c>0, h>=lo`. All-or-nothing row rejection. This is the ONLY bar-level quality check in the entire pipeline.
- No volume anomaly detection, no price jump detection, no stale data detection.

#### 2.6.3 Monitoring
- `market_data/feed_health.py:40`: Monitors tick health (inter-tick deltas, stale detection) but only for **live tick streaming** — not for historical bar ingestion.
- `market_data/spread_monitor.py:34`: Rolling window spread monitoring for live feed. Not backtest.

---

### Summary: Phase 2 Critical Findings

| # | Severity | Finding | File:Line |
|---|----------|---------|-----------|
| 1 | **CRITICAL** | Zero independent reference feed comparison. All data single-source. | Entire repo |
| 2 | **HIGH** | No gap detection or quantification. Cannot determine data completeness. | `scripts/build_features.py:265` (dropna silently) |
| 3 | **HIGH** | No bad tick / spike detection in bar pipeline. | `backtest/data_loader.py:63` (minimal checks only) |
| 4 | **MEDIUM** | No vendor/source changeover detection. Broker changes would contaminate data silently. | N/A |
| 5 | **MEDIUM** | Tick quality modules exist but are test-only, not wired to production pipeline. | `ticks/test_data_quality.py` |
