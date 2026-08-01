# DATA_PIPELINE_FORENSICS.md — Phase 1

## 1.1 — Data Acquisition Layer (MT5-Specific)

- **MT5 function**: `copy_rates_from_pos` and `copy_rates_range` — used in `backtest/data_loader.py:115` and `download_mt5.py:7`
- **Data format**: OHLCV bars. Tick data via `data/mt5_tick_ingester.py` for shadow/live
- **Bar timestamp semantics**: Bar OPEN time (standard MT5 convention). Consistent across codebase.
- **Gap between bar close and availability**: No explicit latency buffer applied in backtest path
- **Timezone**: All timestamps use UTC. MT5 server time → UTC conversion handled in `data/feed.py`
- **DST handling**: UTC throughout — no local timezone conversion issues
- **Unclosed bar**: `backtest/engine.py` iterates from index 1 to total_bars — excludes current forming bar. Live path in `run_paper_trading.py:260` skips same-bar updates. **PASS**

## 1.2 — Storage Layer

- **Raw data storage**: CSV files (`data/EURUSD_D1.csv`, `data/XAUUSD_D1.csv`) + DuckDB (`data_pipeline/storage/duckdb_store.py`)
- **Data mutation**: CSV append-only. DuckDB supports upsert.
- **Data versioning**: No formal versioning. Re-running pipeline may produce different data if source changes.
- **Gap detection**: `backtest/data_loader.py` has basic gap-filling. `data/mt5_tick_ingester.py` tracks gaps.
- **Deduplication**: MT5 data is inherently deduplicated by bar timestamp. No explicit dedup on ingest.

## 1.3 — Feature Engineering Lookahead Audit

| Feature | Defined at | Window | Uses shift()? | Uses .rolling()? | Lookahead Risk | Verdict |
|---------|-----------|--------|---------------|-------------------|----------------|---------|
| return_1 | ml/pipeline.py:95 | 1 | No (pct_change default) | No | None | PASS |
| return_5 | ml/pipeline.py:96 | 5 | No | No | None | PASS |
| rsi_14 | ml/pipeline.py:122 | 14 | No | No | None | PASS |
| atr_14 | ml/pipeline.py:140 | 14 | No | No | None | PASS |
| bb_width | ml/pipeline.py:133 | 20 | No | No | None | PASS |
| volume_ratio | ml/pipeline.py:155 | 20 | No | rolling(20).mean() | None | PASS |
| realized_vol_20 | ml/pipeline.py:166 | 20 | No | rolling(20).std() | None | PASS |
| gk_vol_14 | ml/pipeline.py:178 | 14 | **Yes — .shift(1)** | rolling(14).mean() | **Correctly shifted** | PASS |
| parkinson_vol_14 | ml/pipeline.py:183 | 14 | **Yes — .shift(1)** | rolling(14).mean() | **Correctly shifted** | PASS |
| price_position_20 | ml/pipeline.py:105 | 20 | No | rolling(20).min/max() | None | PASS |
| ema_cross_9_20 | ml/pipeline.py:118 | 9/20 | No | No (EMA) | None | PASS |
| momentum_10 | ml/pipeline.py:195 | 10 | No | No | None | PASS |

### CRITICAL FINDING: SMC Detectors Use `center=True`
`strategies/mlb.py:328-329`:
```python
df["swing_high"] = df["high"].rolling(window=5, center=True).max() == df["high"]
df["swing_low"] = df["low"].rolling(window=5, center=True).min() == df["low"]
```
**center=True is LOOKAHEAD BIAS** — it uses future bars to classify the current bar as a swing point. This is a **P1 finding**: the swing high/low detectors repaint when run bar-by-bar in live mode vs. vectorized on full data.

### Label Construction
`ml/pipeline.py:210`: `forward_return = df["close"].pct_change(10).shift(-10)` — correctly shifted to t+10, no lookahead.

## 1.4 — Train/Validation/Test Boundary Leakage

### Scaler Fitting
`core/ml_pipeline.py:153`: `self._scaler.fit(X)` — fits on full dataset before train/test split. **P1 LEAKAGE**: scaler statistics leak from test set into training.

`ml/pipeline.py:276-282`: `train_test_split(X, y, test_size=0.2, shuffle=False)` — correctly preserves time order. But no scaler is applied in this path.

`validation/walk_forward.py:368`: `model.fit(X_train, y_train_cls)` — no scaler used in WF path. **PASS**

### Feature Selection
No explicit feature selection step found before train/test split. **PASS**

## 1.5 — Timestamp & Alignment Integrity

- Features use `pct_change(N)` which computes `close[t]/close[t-N] - 1` — correctly aligned
- Labels use `pct_change(10).shift(-10)` — correctly shifted forward
- No cross-source merge operations that could introduce timing mismatches
- No ForexFactory calendar data integrated (so no calendar timing risk)

## 1.6 — Leakage Checklist

| Item | Status | Evidence |
|------|--------|----------|
| No future bar data in features | **PARTIAL FAIL** | `strategies/mlb.py:328-329` center=True swing detectors |
| Rolling windows use min_periods, not center=True | **FAIL** | mlb.py:328 uses center=True |
| Scaler fit only on training fold | **FAIL** | core/ml_pipeline.py:153 fits on full data |
| Label aligned to correct future bar | PASS | ml/pipeline.py:210 |
| No backfill (bfill) in features | PASS | fillna(0) used, not bfill |
| Bar timestamp semantics consistent | PASS | UTC throughout |
| DST transitions handled | PASS | UTC — no DST |
| Unclosed bar excluded from live decisions | PASS | run_paper_trading.py:260 |
| Calendar data joined by event time | N/A | No calendar data |
| No cross-fold contamination in normalization | **FAIL** | core/ml_pipeline.py:153 |

## 1.7 — Multi-Account / Multi-Server Consistency

Single account/single server (Pepperstone). Check is N/A.

## 1.8 — Holiday, Low-Liquidity & Market-Structure Calendar Handling

- `core/rollover_filter.py` exists but is **ORPHANED** (not wired into TradingLoop)
- `risk/market_session_guard.py` has session-aware blocking but **PARTIALLY WIRED**
- No explicit holiday exclusion in backtest or live code
- Crypto (BTCUSD/ETHUSD) trades 24/7 — no weekend close logic found for crypto specifically. Rollover filter would incorrectly block crypto during FX rollover window if wired.

## 1.9 — Leakage-Fix Re-Verification

`core/cross_validation.py` implements CPCV with embargo. `validation/walk_forward.py:59` default `embargo_bars=12`. The CPCV implementation is wired into `validation/walk_forward.py` and `core/walk_forward.py`. **Wired but [FIX UNVERIFIED — only current state confirmed, prior buggy state not re-tested]** per R13.

Training accuracy from `ml/pipeline.py:300`: uses XGBoost with early stopping — no suspiciously perfect results observed in code. But actual training runs not examined.

---

**P0 Findings**: 0
**P1 Findings**: 3 (center=True swing detectors, scaler leakage, rollover filter orphaned)
**P2 Findings**: 1 (holiday handling absent)
