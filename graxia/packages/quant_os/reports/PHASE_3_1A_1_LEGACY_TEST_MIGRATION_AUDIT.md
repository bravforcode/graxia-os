# Phase 3.1A.1 — Legacy Test Migration Audit

**Audit date:** Phase 3.1A.1  
**Canonical API reference:** `BacktestConfig` in `backtest/engine.py:88`

## Canonical fields (current)

| Field | Type | Default |
|---|---|---|
| `risk_per_trade_bps` | int | 10 |
| `units_per_lot` | — | **removed** |
| `strict_mtf` | bool | True |

---

## Audit Table

| Test file | Original purpose | Migration changes | Risk conversion verified | Classification | Decision |
|---|---|---|---|---|---|
| `test_single.py` | Single-strategy backtest smoke test (OrderBlock, D1+H1+M15) | No `risk_per_trade_pct`, no `units_per_lot`, `strict_mtf=False` set explicitly | N/A — uses default bps=10 | ACTIVE | keep |
| `test_timing.py` | Timing benchmark: all 13 strategies with full multi-TF data (N=200 D1, 5000 H1, 20000 M15) | Same config as test_single — no legacy fields | N/A — uses default bps=10 | ACTIVE | keep |
| `test_timing2.py` | Timing benchmark: all 13 strategies, D1 only (no multi-TF, N=100) | Same config — no legacy fields | N/A — uses default bps=10 | ACTIVE | keep |
| `test_timing3.py` | Timing benchmark: all 13 strategies, small multi-TF (500 H1, 2000 M15, N=100) | Same config — no legacy fields | N/A — uses default bps=10 | ACTIVE | keep |
| `test_vwap.py` | VWAPRejectionStrategy single-strategy backtest + manual `analyze()` call | **NOT migrated** — still uses `risk_per_trade_pct=1.0` and `units_per_lot=100` | **FAIL** — `risk_per_trade_pct` no longer exists in BacktestConfig; `1.0% = 100 bps` conversion would be correct semantically but the field doesn't exist | RETIRED | retire |

---

## Notes

### test_single.py, test_timing.py, test_timing2.py, test_timing3.py
- All four tests use `BacktestConfig(strict_mtf=False, initial_capital=10000, slippage_pips=0.5, commission_per_lot=3.5)` with no risk/units params.
- They rely on the canonical default `risk_per_trade_bps=10`.
- `strict_mtf=False` is intentionally set (not default) — these tests tolerate missing multi-TF data.
- No legacy fields present. Migration complete.

### test_vwap.py
- **Fails on load** — `load_csv_data` raises `ValueError: No valid data found` because the date format `'%Y-%m-%d %H:%M:%S%z'` (with timezone) doesn't match the actual CSV format `'%Y-%m-%d %H:%M:%S'` (no timezone).
- Even if the date format were fixed, `BacktestConfig(risk_per_trade_pct=1.0, units_per_lot=100)` would raise `TypeError` — those fields no longer exist in the canonical dataclass.
- The test's actual purpose (VWAPRejectionStrategy smoke test) is covered by `test_timing.py` which runs all 13 strategies including VWAPRejection.
- `test_vwap.py` also includes a manual `analyze()` call — this logic is trivial and not worth preserving as a standalone test.
- **Data file exists:** `XAUUSD_D1.csv` confirmed present.

---

## Summary

| Classification | Count | Files |
|---|---|---|
| ACTIVE | 4 | test_single.py, test_timing.py, test_timing2.py, test_timing3.py |
| RETIRED | 1 | test_vwap.py |
| QUARANTINED | 0 | — |
| LEGACY_COMPATIBILITY | 0 | — |
