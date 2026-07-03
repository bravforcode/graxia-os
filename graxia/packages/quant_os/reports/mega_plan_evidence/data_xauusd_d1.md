# Data Truth: XAUUSD_D1 Quarantine

**Generated:** 2026-07-01
**Script:** `scripts/quarantine_xauusd_d1.py`

## Source File
- `data/XAUUSD_D1.csv` — 20,300 raw rows (1793-03-01 to 2026-07-01)

## Quarantine Rules
| Rule | Description |
|------|-------------|
| `drop_pre_2004` | Remove rows before 2004-01-01 (pre-modern gold era, flat synthetic prices at 19.39) |
| `drop_high_lt_low` | Remove rows where High < Low (impossible) |
| `drop_high_lt_max_oc` | Remove rows where High < max(Open, Close) |
| `drop_low_gt_min_oc` | Remove rows where Low > min(Open, Close) |
| `drop_nonpositive_ohlc` | Remove rows where any OHLC <= 0 |

## Results
| Metric | Count |
|--------|-------|
| Raw rows | 20,300 |
| Pre-2004 rows (quarantined) | 9,494 |
| OHLC violation: H < L | 1 |
| OHLC violation: H < max(O,C) | 236 |
| OHLC violation: L > min(O,C) | 227 |
| Non-positive prices | 0 |
| **Total quarantined** | **9,880** |
| **Clean rows** | **10,420** |

## Outputs
- **Clean data:** `data/canonical/XAUUSD_D1_clean.csv` (10,420 rows, 2004-01-02 to 2026-07-01)
- **Quarantined rows:** `data/quarantine/XAUUSD_D1_quarantined.csv` (9,880 rows, preserved for audit)
- **Manifest:** `data/manifests/XAUUSD_D1_clean.manifest.json`

## Key Findings
1. **47% of raw data was pre-2004 synthetic filler** — constant price of 19.39 from 1793-2003. This data would poison any ML model.
2. **464 OHLC integrity violations detected** in the remaining data — these rows have impossible price relationships.
3. **Clean dataset spans 22.5 years** of modern gold pricing (2004-2026), sufficient for robust backtesting.

## Verification
```bash
python scripts/quarantine_xauusd_d1.py
# Expected: 10,420 clean rows, 9,880 quarantined
```
