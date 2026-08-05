# Data Inventory — Phase 2 (Data Infrastructure)

Generated: 2026-07-13

## Summary

| Category | Count | Status |
|----------|-------|--------|
| OHLCV CSV files (root) | 148 | ✅ Present |
| Parquet files | 12 | ✅ Present |
| Tick parquet files | 6 | ✅ Present |
| Sacred holdout | 1 | ✅ Untouched |
| Instruments with H1 data | 15 | ✅ 50k rows each |
| Instruments with D1 data | 16 | ✅ Deep history |
| Cost calibration (measured) | 10 | ✅ MEASURED |
| Cost calibration (estimated) | 6 | ✅ Updated to ESTIMATED |
| Tick data for spread measurement | 6 | ✅ Available |

---

## OHLCV Data — H1 (Primary Backtest Frame)

All H1 files have exactly 50,000 rows (MT5 export cap). Date ranges:

| Symbol | Rows | First Date | Last Date | Years |
|--------|------|------------|-----------|-------|
| AUDUSD | 50,000 | 2018-06-12 | 2026-06-26 | ~8.0 |
| BTCUSD | 50,000 | 2020-06-10 | 2026-06-26 | ~6.0 |
| ETHUSD | 50,000 | 2020-06-10 | 2026-06-26 | ~6.0 |
| EURUSD | 50,000 | 2018-06-01 | 2026-06-19 | ~8.0 |
| GBPUSD | 50,000 | 2018-06-01 | 2026-06-19 | ~8.0 |
| NAS100 | 50,000 | 2018-01-02 | 2026-06-26 | ~8.5 |
| NZDUSD | 50,000 | 2018-06-12 | 2026-06-26 | ~8.0 |
| US30   | 50,000 | 2018-02-28 | 2026-06-26 | ~8.3 |
| USDCAD | 50,000 | 2018-06-13 | 2026-06-26 | ~8.0 |
| USDCHF | 50,000 | 2018-06-13 | 2026-06-26 | ~8.0 |
| USDJPY | 50,000 | 2018-06-13 | 2026-06-26 | ~8.0 |
| XAGUSD | 50,000 | 2018-01-11 | 2026-06-26 | ~8.5 |
| XAUUSD | 50,000 | 2017-12-21 | 2026-06-20 | ~8.5 ✅ |
| XPDUSD | 50,000 | 2017-12-12 | 2026-06-26 | ~8.5 |
| XPTUSD | 50,000 | 2018-01-09 | 2026-06-26 | ~8.5 |

**XAUUSD_H1.csv**: 8.5 years of data (2017-12-21 to 2026-06-20). Exceeds the 5-year requirement. ✅

### Gaps
- OIL (SpotCrude): **No H1 CSV file exists.** Only FRED daily data available (`data/fred/daily/DCOILWTICO.csv`).
- XAUUSD_H1 ends 2026-06-20 (6 days behind other symbols as of inventory date).

---

## OHLCV Data — D1 (Deep History)

| Symbol | Rows | First Date | Last Date | Span |
|--------|------|------------|-----------|------|
| AUDUSD | 14,508 | 1971-01-04 | 2026-06-29 | 55yr |
| BTCUSD | 5,827 | 2010-07-17 | 2026-06-29 | 16yr |
| DXY    | 2,143 | 2018-01-02 | 2026-07-10 | 8yr |
| ETHUSD | 3,980 | 2015-08-07 | 2026-06-29 | 11yr |
| EURUSD | 14,220 | 1971-01-04 | 2026-06-29 | 55yr |
| GBPUSD | 14,490 | 1900-03-01 | 2026-06-29 | 126yr |
| NAS100 | 23,176 | 1938-01-03 | 2026-06-29 | 88yr |
| NZDUSD | 14,383 | 1971-01-04 | 2026-06-29 | 55yr |
| US30   | 33,732 | 1896-05-27 | 2026-06-29 | 130yr |
| USDCAD | 14,428 | 1971-01-04 | 2026-06-29 | 55yr |
| USDCHF | 14,427 | 1971-01-04 | 2026-06-29 | 55yr |
| USDJPY | 14,462 | 1971-01-04 | 2026-06-29 | 55yr |
| XAGUSD | 16,671 | 1792-03-01 | 2026-06-29 | 234yr |
| XAUUSD | 20,300 | 1793-03-01 | 2026-07-01 | 233yr |
| XPDUSD | 2,307 | 2017-07-14 | 2026-06-26 | 9yr |
| XPTUSD | 3,646 | 2012-09-02 | 2026-06-26 | 14yr |

---

## Other Timeframes

Additional CSV files exist for M1, M5, M15, M30, H4, W1, MN1 for all 15 tradeable symbols. Key notes:
- M1/M5: 5,000 rows each (short windows, ~1-3 weeks)
- M15: 50,000-62,881 rows (~1-2 years)
- M30: 50,000 rows (~2-4 years)
- H4: 13,000-25,000 rows (~6-16 years)
- W1/MN1: Full history available

---

## Parquet Files

| File | Size | Content |
|------|------|---------|
| `mt5_xauusd_h1_10yr.parquet` | 1.88 MB | XAUUSD H1 10-year export |
| `cot/gold_cot_weekly.parquet` | — | Gold COT disaggregated futures |
| `cot/silver_cot_weekly.parquet` | — | Silver COT disaggregated futures |
| `macro/yf_VIXCLS.parquet` | — | VIX close |
| `macro/yf_GVZCLS.parquet` | — | Gold VIX |
| `macro/yf_DTWEXBGS.parquet` | — | Trade-weighted USD index |
| `macro/yf_DFII10.parquet` | — | 10yr TIPS yield |
| `macro/VIXCLS_*.parquet` | — | VIX date-range snapshot |
| `macro/DFII10_*.parquet` | — | TIPS date-range snapshot |
| `cot/cot_xauusd_disaggregated_fut_2024.parquet` | — | Gold COT 2024 |
| `cot/cot_xauusd_disaggregated_fut_2025.parquet` | — | Gold COT 2025 |
| `cot/cot_xauusd_disaggregated_fut_2026.parquet` | — | Gold COT 2026 |

---

## Tick Data (data/ticks/)

| File | Size | Symbol |
|------|------|--------|
| `BTCUSD_ticks_24h.parquet` | 7.44 MB | BTCUSD |
| `EURUSD_ticks_24h.parquet` | 3.70 MB | EURUSD |
| `GBPUSD_ticks_24h.parquet` | 5.10 MB | GBPUSD |
| `US30_ticks_24h.parquet` | 2.41 MB | US30 |
| `USDJPY_ticks_24h.parquet` | 3.51 MB | USDJPY |
| `XAUUSD_ticks_24h.parquet` | 6.91 MB | XAUUSD |

24-hour tick snapshots. Usable for spread measurement via `scripts/measure_real_spread.py`.

---

## Sacred Holdout

`data/sacred_holdout/holdout.csv` — 260 rows, XAUUSD daily with DXY and TIPS yields.
**NOT MODIFIED.** Untouched by this phase.

---

## Cost Calibration Status

### config/cost_calibration.json (v2.2)

| Asset | Status | RT Cost (bps) | Source |
|-------|--------|---------------|--------|
| BTCUSD | MEASURED | 4.86 | 20 samples, 2026-07-03 |
| ETHUSD | MEASURED | 23.34 | 20 samples, 2026-07-03 |
| EURUSD | MEASURED | 7.00 | 20 samples, 2026-07-03 |
| GBPUSD | MEASURED | 7.30 | 20 samples, 2026-07-03 |
| OIL    | MEASURED | 9.76 | 20 samples, 2026-07-03 |
| USDJPY | MEASURED | 7.12 | 20 samples, 2026-07-03 |
| XAGUSD | MEASURED | 13.16 | 20 samples, 2026-07-03 |
| XAUUSD | MEASURED | 0.72 | 20 samples, 2026-07-03 |
| XPDUSD | MEASURED | 110.70 | 1 sample, 2026-07-12 |
| XPTUSD | MEASURED | 90.58 | 1 sample, 2026-07-12 |
| USDCAD | **ESTIMATED** | 7.5 | Broker published baseline |
| USDCHF | **ESTIMATED** | 8.0 | Broker published baseline |
| AUDUSD | **ESTIMATED** | 7.5 | Broker published baseline |
| NZDUSD | **ESTIMATED** | 8.5 | Broker published baseline |
| NAS100 | **ESTIMATED** | 15.0 | Broker published baseline |
| US30   | **ESTIMATED** | 20.0 | Broker published baseline |

**162 total measurement samples across 10 MEASURED assets. 6 assets carry ESTIMATED costs.**

---

## Missing Data / Action Items

| Item | Priority | Action |
|------|----------|--------|
| OIL H1 CSV | Medium | Download via MT5 or use FRED daily as fallback |
| XAUUSD_H1 last 6 days | Low | Re-export from MT5 to bring to current |
| Live spread measurement for 6 estimated assets | High | Run `scripts/measure_real_spread.py --mode live` when MT5 connected |
| Tick data for USDCAD, USDCHF, AUDUSD, NZDUSD, NAS100 | Medium | Collect via `scripts/collect_ticks.py` |
| XAUUSD_M1_extended.csv | — | Empty file (0 data rows), can be removed |

---

## Data Integrity Notes

- All CSV files use standard format: `time,open,high,low,close,volume`
- No corrupted files detected
- XAUUSD_D1_yfinance.csv has `Ticker` as first data value (header artifact) — non-critical
- EURUSD_D1_clean.csv and EURUSD_daily_yf.csv are yfinance-derived duplicates
- `data/multi_symbol_log.csv` and `data/sample_trades.csv` are trade logs, not market data
