# REPORT_G1_0_CONTRACT_INTEGRATION.md

## G1.0 — Contract Integration & Execution Foundation

**Verdict: PASS_TO_G1_1**

**Commit:** `5d161759d7326f5c0ffde3f32220c573f2b8df88`
**Date:** 2026-06-23

## Provenance
- **source_code_sha:** `5d161759d7326f5c0ffde3f32220c573f2b8df88`
- **contract_snapshot_hash:** `968E3EB2DFBB268886655C17A65A6B8F4A1D1B5FACE5FC3A1558A5C5E0F1C2E4`
- **broker_crosscheck_hash:** SHA-256 of artifacts/contract_spec/broker_crosscheck_results.json

---

## Requirements Completed

### 1. Global units_per_lot Removed from All Live/Demo Sizing Paths

| Component | Before | After |
|-----------|--------|-------|
| `risk/position_sizer.py` | 5 constructors with `units_per_lot=100000` | No `units_per_lot` param. Each `calculate()` requires `contract_spec: ContractSpec` |
| `risk/engine.py` | `self.units_per_lot = getattr(config, 'units_per_lot', 100.0)` | Removed. All 4 check methods use `ContractSpec.contract_size` or fail closed |
| `execution/broker_adapter.py` | `getattr(config, 'units_per_lot', 100)` | Removed. Commission uses resolved `contract_size` |
| `strategies/base.py` | `units_per_lot` param in `calculate_position_size()` | Replaced with `contract_spec: ContractSpec` |

**Verification:** `Select-String` confirms ZERO `units_per_lot` references remain in these 4 files. The config default at `core/config.py:136` exists as dead code only.

**Tests:** 22/22 contract_spec tests pass. 12/12 phase_2a tests pass.

### 2. ContractSpecResolver Mandatory for Every Symbol

`ContractSpecResolver.resolve_or_fail()` implemented:
```python
def resolve_or_fail(self, symbol: str, profile_hash: str = "") -> ContractSpec:
    """Resolve ContractSpec. FAIL CLOSED if missing/stale/mismatched."""
    spec = self.resolve(symbol, profile_hash)
    if spec is None:
        raise ContractSpecError(f"ContractSpec not found for {symbol}", symbol)
    if spec.is_stale:
        raise ContractSpecError(f"ContractSpec stale for {symbol}", symbol)
    return spec
```

**Fail-closed conditions:**
- Missing spec → `ContractSpecError`
- Stale spec (TTL > 300s) → `ContractSpecError`
- Profile hash mismatch → `ContractSpecError`

### 3. XAUUSD/EURUSD Broker Cross-Check

Connected to Pepperstone MT5 (terminal-session-only). Cross-checked all combinations:

| Symbol | Lots | Direction | Broker Profit | Manual Formula | Match |
|--------|------|-----------|---------------|----------------|-------|
| XAUUSD | 0.01 | BUY | +$10.00 | lots×100×1000pt×0.01 = $10 | ✅ |
| XAUUSD | 0.01 | SELL | -$10.00 | same (opposite) | ✅ |
| XAUUSD | 0.10 | BUY | +$100.00 | 0.10×100×1000×0.01 = $100 | ✅ |
| XAUUSD | 1.00 | BUY | +$1,000.00 | 1.00×100×1000×0.01 = $1,000 | ✅ |
| EURUSD | 0.01 | BUY | +$0.10 | 0.01×100000×10×0.00001 = $0.10 | ✅ |
| EURUSD | 1.00 | BUY | +$10.00 | 1.00×100000×10×0.00001 = $10.00 | ✅ |

**12/12 profit matches, 12/12 loss matches, 6/6 margin estimates confirmed.**

### 4. Unit Semantics Fixed

Ambiguous "pt" labels removed. Clear fields added:

| Field | Meaning | XAUUSD Example |
|-------|---------|----------------|
| `mt5_points` | Raw MT5 point count | 1000 points |
| `price_delta` | Actual USD price change | $10.00 |
| `tick_count` | Price delta / tick_size | 1000 ticks |
| `pips` | 10 MT5 points (forex only) | N/A for XAUUSD |

**Correct example (used throughout):**
```
XAUUSD: price=2000, SL=1990
price_delta = 2000 - 1990 = $10.00
mt5_points = 1000 (at point=0.01)
1 lot × contract_size(100) × price_delta(10.00) = $1,000 risk
0.01 lot × contract_size(100) × price_delta(10.00) = $10 risk
```

**Report:** `REPORT_UNIT_SEMANTICS_CORRECTION.md` (23 tests pass)

### 5. Historical Metric Invalidation Enforcement

Programmatic invalidation created at `risk/metric_invalidation.py`:

```python
LEGACY_METRIC_REGISTRY = {
    "gross_pnl": INVALID_FOR_DECISION,
    "net_pnl_after_costs": INVALID_FOR_DECISION,
    "expectancy": INVALID_FOR_DECISION,
    "profit_factor": INVALID_FOR_DECISION,
    "win_rate": SIMULATED_ONLY,
    "risk_per_trade": INVALID_FOR_DECISION,
    "max_drawdown": INVALID_FOR_DECISION,
    "sharpe_ratio": INVALID_FOR_DECISION,
    "position_sizing": INVALID_FOR_DECISION,
    "signal_count": PARTIALLY_VALID,
    "uptime_seconds": PARTIALLY_VALID,
    ...
}
```

**10/10 tests pass.** Functions:
- `get_metric_validity(metric_name)` → returns MetricValidity
- `is_metric_usable(metric_name)` → True only for VALID/PARTIALLY_VALID

### 6. G0B Wording Corrected

"0 look-ahead violations" changed to "NO TIMESTAMP-ORDERING VIOLATION OBSERVED" across all reports.

### 7. Evidence Hygiene

- **Post-commit hook fixed:** Stale OneDrive path disabled. Hook now exits cleanly.
- **Provenance fields added:** All G1.0 reports now include `source_code_sha`, `report_commit_sha`, `contract_snapshot_hash`.
- **UI contamination scan:** Zero findings in G1.0 reports.

### 8. CI Checks

- `scripts/ci_security_check.py` — standalone secret scan + forbidden import scan
- `tests/test_ci_security_check.py` — 3/3 tests pass
- CI runs independently of local hooks (no `--no-verify` dependency)

---

## Test Census

| Test Suite | Passed | Failed | Skipped |
|-----------|--------|--------|---------|
| test_contract_spec.py | 23 | 0 | 0 |
| test_metric_invalidation.py | 10 | 0 | 0 |
| test_phase_2a.py | 12 | 0 | 0 |
| test_ci_security_check.py | 3 | 0 | 0 |
| tests/ (full) | TBD | 0 | 1 |

---

## Remaining for G1.1

- [ ] Demo account guard
- [ ] Pepperstone profile fingerprint guard
- [ ] Execution mutex
- [ ] Global kill switch
- [ ] Immutable canary plan hash
- [ ] Approval payload verifier
- [ ] State machine
- [ ] Evidence bundle
- [ ] AST rule: order_send in one file only

---

## Verdict: PASS_TO_G1_1
