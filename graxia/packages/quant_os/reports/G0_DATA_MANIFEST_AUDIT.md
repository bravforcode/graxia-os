# G0.9 — Data Manifest Audit

**Date**: 2026-06-22
**Scope**: All CSV data files and manifest JSON in `graxia/packages/quant_os/data/`

---

## 1. XAUUSD Data

| Metric | D1 | H1 | M15 |
|--------|-----|-----|------|
| File size | 289 KB | 2.88 MB | 2.86 MB |
| Row count | 5,000 | 50,000 | 50,000 |
| Date range | 2007-01-23 → 2026-06-19 | 2017-12-21 → 2026-06-20 | 2024-05-03 → 2026-06-20 |
| Source | MT5 | MT5 | MT5 |
| Timezone | UTC | UTC | UTC |
| Status | VALIDATED | VALIDATED | VALIDATED |

### Checksum Verification (XAUUSD)

| File | Manifest SHA-256 | Actual SHA-256 | Match |
|------|-------------------|----------------|-------|
| XAUUSD_D1.csv | `e99edf4839f6935313bd0babc27352f11d17cc626afb9017fbc43d84060d976e` | `e99edf4839f6935313bd0babc27352f11d17cc626afb9017fbc43d84060d976e` | **YES** |
| XAUUSD_H1.csv | `ad20fbabc1f2066014c6e4197b52acea5b618b95ae0b2a2762d6a314a8352702` | `ad20fbabc1f2066014c6e4197b52acea5b618b95ae0b2a2762d6a314a8352702` | **YES** |
| XAUUSD_M15.csv | `d2606c545920d81b5d33b97a2a14772337100fc88a22a2a6f72f8b7bd89824cc` | `d2606c545920d81b5d33b97a2a14772337100fc88a22a2a6f72f8b7bd89824cc` | **YES** |

Manifest file SHA-256 (for freeze reference):

| Manifest File | SHA-256 |
|---------------|---------|
| `data/manifests/XAUUSD_D1.manifest.json` | `SHA256_OF_MANIFEST_D1` |
| `data/manifests/XAUUSD_H1.manifest.json` | `SHA256_OF_MANIFEST_H1` |
| `data/manifests/XAUUSD_M15.manifest.json` | `SHA256_OF_MANIFEST_M15` |

---

## 2. EURUSD Data

| Metric | D1 | H1 | M15 | X (Yahoo) |
|--------|-----|-----|------|-----------|
| File size | 309 KB | 2.97 MB | 2.94 MB | 146 KB |
| Row count | 5,000 | 50,000 | 50,000 | 1,304 |
| Date range | 2007-03-20 → 2026-06-19 | 2018-06-01 → 2026-06-19 | 2024-06-13 → 2026-06-19 | 2020-01-01 → 2024-12-30 |
| Source | MT5 | MT5 | MT5 | Yahoo Finance |
| Timezone | UTC | UTC | UTC | UTC (+tz suffix) |
| Status | N/A | N/A | N/A | N/A |

### Checksum Verification (EURUSD)

No manifest files exist for EURUSD. Actual SHA-256 of CSV files:

| File | Actual SHA-256 |
|------|----------------|
| EURUSD_D1.csv | `3aeb4198061da45a214fc45c19ed9e1310fc4d71d3664d4b0c5569df1eefe67f` |
| EURUSD_H1.csv | `1afe495dd115d0040fa8e08a965f2fec41e9dcec932c6ff83974196926f49847` |
| EURUSD_M15.csv | `5625088839537d583a4b5c2a44c19bca0f69f54fa43392dac6531377c2db5496` |
| EURUSD_X.csv | `d6ea0c4fc8b705b9b38f0edbb878591f09bb0d169d839f3f95976110b4ef9b5b` |

---

## 3. GBPUSD Data

| Metric | D1 | H1 | M15 |
|--------|-----|-----|------|
| File size | 328 KB | 3.12 MB | 3.11 MB |
| Row count | 5,000 | 50,000 | 50,000 |
| Date range | 2007-03-20 → 2026-06-19 | 2018-06-01 → 2026-06-19 | 2024-06-13 → 2026-06-19 |
| Source | MT5 | MT5 | MT5 |
| Timezone | UTC | UTC | UTC |
| Status | N/A | N/A | N/A |

### Checksum Verification (GBPUSD)

No manifest files exist for GBPUSD. Actual SHA-256 of CSV files:

| File | Actual SHA-256 |
|------|----------------|
| GBPUSD_D1.csv | `bf2259014d36aa1c49bb141d6805bb12333bc9984ba9b77fd99b331ca6d2f2c1` |
| GBPUSD_H1.csv | `5d402c308bfbd533910082f61d2d163efa8b6dc5d9bbb7ad886d785a02de5258` |
| GBPUSD_M15.csv | `00e2655d437e7aa1b4fa2e8fc42781ad64aff39b5e61e448119fb3bfd82b191f` |

---

## 4. Data Quality Notes

### Duplicate Timestamps
Zero duplicates across all 9 MT5 CSV files.

### Header Consistency
All MT5 CSVs use identical schema: `time,open,high,low,close,volume`.

### EURUSD_X.csv — Schema Mismatch
`EURUSD_X.csv` (Yahoo Finance source) has a different schema:
- Headers: `Date,Open,High,Low,Close,Volume,Dividends,Stock Splits`
- Column names capitalized (not lowercase)
- Timestamps include timezone suffix (`+00:00`)
- Contains extra columns (`Dividends`, `Stock Splits`) — both always zero
- 1,304 rows vs 5,000–50,000 for MT5 data — significantly smaller

**Action needed**: If EURUSD_X.csv feeds into the same pipeline as MT5 data, it requires a schema normalization step.

### Missing Manifests
- XAUUSD: D1/H1/M15 all have manifests ✅
- EURUSD: **No manifests** for any timeframe
- GBPUSD: **No manifests** for any timeframe

### Data Freshness
- XAUUSD D1 ends 2026-06-19, H1/M15 end 2026-06-20
- EURUSD/GBPUSD D1 end 2026-06-19, H1/M15 end 2026-06-19
- All datasets are within 1–3 days of today (2026-06-22). Fresh.

### Row Count Pattern
D1 files capped at exactly 5,000 rows. H1/M15 capped at exactly 50,000 rows. These appear to be download limits from MT5, not natural data boundaries. The actual historical depth available from MT5 may exceed what was downloaded.

---

## 5. Freeze Reference (XAUUSD)

### CSV File SHA-256
```
e99edf4839f6935313bd0babc27352f11d17cc626afb9017fbc43d84060d976e  XAUUSD_D1.csv
ad20fbabc1f2066014c6e4197b52acea5b618b95ae0b2a2762d6a314a8352702  XAUUSD_H1.csv
d2606c545920d81b5d33b97a2a14772337100fc88a22a2a6f72f8b7bd89824cc  XAUUSD_M15.csv
```

### Manifest File SHA-256
```
9e33c45409944b15f7c8ee796840ea41860d6e6a610266790595f10c08e564de  XAUUSD_D1.manifest.json
c118b6d5a8c73efc8804c0bf03e0814a2405b8db1514d817681267729c80a398  XAUUSD_H1.manifest.json
67df2780b599c0083c12a3ef3e1a34ee29e7167fc0bc1a787611ed566e3b7a1f  XAUUSD_M15.manifest.json
```

---

## Summary

| Item | Status |
|------|--------|
| XAUUSD manifests exist | ✅ All 3 |
| XAUUSD checksums verified | ✅ All match |
| EURUSD manifests exist | ❌ None |
| GBPUSD manifests exist | ❌ None |
| Duplicate timestamps | ✅ Zero across all files |
| Schema consistency (MT5) | ✅ Identical |
| EURUSD_X schema | ⚠️ Different — needs normalization |
| Data freshness | ✅ All within 3 days |
| Downloads appear capped | ℹ️ D1=5K, H1/M15=50K rows |
