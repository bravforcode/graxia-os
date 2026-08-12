# Multi-Asset Overlap Truth Table

**Generated:** 2026-07-02 15:13 UTC
**Assets:** XAUUSD, EURUSD, BTCUSD, ETHUSD

## Per-Asset Coverage

| Asset | First Date | Last Date | Rows | Unique Days | Expected WD | Missing WD | Coverage % |
|-------|-----------|-----------|------|-------------|-------------|------------|------------|
| XAUUSD | 1793-03-01 | 2026-07-01 | 20300 | 15305 | 60874 | 45771 | 24.81% |
| EURUSD | 1971-01-04 | 2026-06-29 | 14220 | 14220 | 14476 | 256 | 98.23% |
| BTCUSD | 2010-07-17 | 2026-06-29 | 5827 | 5827 | 4161 | 0 | 100.0% |
| ETHUSD | 2015-08-07 | 2026-06-29 | 3980 | 3980 | 2842 | 0 | 100.0% |

## Pairwise Overlap

| Pair | Overlap Start | Overlap End | Overlap Days | Rows A | Rows B |
|------|--------------|-------------|-------------|--------|--------|
| XAUUSD/EURUSD | 1971-01-04 | 2026-06-29 | 20265 | 19183 | 14220 |
| XAUUSD/BTCUSD | 2010-07-17 | 2026-06-29 | 5826 | 8220 | 5827 |
| XAUUSD/ETHUSD | 2015-08-07 | 2026-06-29 | 3979 | 5615 | 3980 |
| EURUSD/BTCUSD | 2010-07-17 | 2026-06-29 | 5826 | 4143 | 5827 |
| EURUSD/ETHUSD | 2015-08-07 | 2026-06-29 | 3979 | 2828 | 3980 |
| BTCUSD/ETHUSD | 2015-08-07 | 2026-06-29 | 3979 | 3980 | 3980 |

## Full Portfolio Overlap

- **Window:** 2015-08-07 to 2026-06-29
- **Overlap days:** 3979
- **Overlap years:** 10.9

## Key Findings

1. Full portfolio overlap is **3979 days** (10.9 years), constrained by the shortest-history asset.
3. **XAUUSD** has 45771 missing weekdays (75.19% gap) — investigate data source.
3. **EURUSD** has 256 missing weekdays (1.769999999999996% gap) — investigate data source.

## Verification
```bash
python scripts/build_overlap_truth_table.py
```
