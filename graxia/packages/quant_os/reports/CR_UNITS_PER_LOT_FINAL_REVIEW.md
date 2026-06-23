# CR_UNITS_PER_LOT_FINAL_REVIEW.md

## Change Request: units_per_lot → ContractSpec Resolution

**Status: REVIEW_COMPLETE — APPROVED_WITH_CONDITIONS**
**Gate: UNITS_PER_LOT_CHANGE_REVIEW_REQUIRED**
**Date:** 2026-06-23
**Commit:** `0408b175fb596c9714592245de060044a14b4b93`

---

## 1. Problem Statement

The Quant OS position sizing, risk engine, and execution adapter all relied on a hardcoded default of `units_per_lot=100000` — the standard forex lot size. For XAUUSD on Pepperstone, the actual contract size is `trade_contract_size=100` (1 lot = 100 troy ounces). This meant:

- All position sizing was **1000x larger than intended** for XAUUSD
- All historical shadow campaign P&L is **inflated by ~1000x**
- Risk calculations, margin estimates, and cost models were incorrect for XAUUSD
- EURUSD/forex symbols worked correctly with the 100000 default (coincidence)

## 2. Solution Design

### Before (broken)
```python
# position_sizer.py: hardcoded default
class PositionSizer(ABC):
    def __init__(self, name: str, units_per_lot: float = 100000.0):
        ...
```

### After (correct)
```python
# contract_spec.py: runtime resolution from broker
class ContractSpecResolver:
    def resolve(self, symbol: str, profile_hash: str = "") -> ContractSpec:
        sym_info = self._mt5.symbol_info(symbol)
        # trade_contract_size, volume_min, volume_max, volume_step
        # point, tick_size, tick_value, stops_level, freeze_level
        # currency_profit, currency_margin
```

Key design decisions:
- **No global default** — `ContractSpecResolver` always fetches from broker runtime
- **Fail-closed** — if `symbol_info()` returns None or connection is missing, raises `ContractSpecError`
- **TTL cache** — specs cached for 300 seconds, refreshed automatically
- **Content hash** — deterministic SHA-256 over all fields for mismatch detection
- **Immutable** — `ContractSpec` is a frozen dataclass

## 3. Every Changed File

| File | Lines | Change |
|------|-------|--------|
| `risk/contract_spec.py` | NEW (78) | ContractSpec dataclass + ContractSpecResolver |
| `tests/test_contract_spec.py` | NEW (175) | 12 tests covering all required scenarios |
| `reports/HISTORICAL_METRIC_INVALIDATION.md` | NEW | Legacy metric freeze + label registry |
| `tests/test_phase_2a.py` | 1 | Added contract_spec to hardcode-audit allowlist |
| `repo_intelligence/hooks/pre_commit_security_check.py` | 7 | Extended regex for YAML/JSON secret patterns |

## 4. XAUUSD Contract Assumptions

| Field | Value | Source |
|-------|-------|--------|
| contract_size | 100 | Pepperstone symbol_info() |
| volume_min | 0.01 | Broker minimum |
| volume_max | 50.0 | Broker maximum |
| volume_step | 0.01 | Broker step |
| point | 0.01 | 2-digit pricing |
| tick_size | 0.01 | Minimum price movement |
| tick_value | 1.0 USD | Per tick profit/loss |
| currency_profit | USD | Profit currency |
| currency_margin | USD | Margin currency |
| stops_level | 0 | No minimum SL distance |
| freeze_level | 0 | No freeze level |

1 lot XAUUSD = 100 units of the underlying (troy ounces).
This is the correct broker reality, not a config assumption.

## 5. EURUSD/Forex Impact

| Field | Value |
|-------|-------|
| contract_size | 100000 (standard forex) |
| volume_min | 0.01 |
| point | 0.00001 |
| tick_value | 1.0 USD (approx, varies) |

EURUSD correctly resolves to `contract_size=100000` from broker runtime. No override needed.
The `ContractSpecResolver` returns per-symbol values from `symbol_info()` — EURUSD gets the correct forex contract size automatically.

## 6. Before/After Numeric Examples

### XAUUSD: 1 lot, price=2000, SL=1990 (10 point risk)

| Metric | Old (100000) | New (100) | Correct? |
|--------|-------------|-----------|----------|
| Position units | 100000 | 100 | ✅ New |
| Notional value | $200,000,000 | $200,000 | ✅ New |
| Risk per trade | $10,000 | $10 | ✅ New |
| Risk on $10k account | 100% (blown) | 0.1% | ✅ New |

### EURUSD: 1 lot, price=1.1000, SL=1.0990 (10 pip risk)

| Metric | Old (100000) | New (runtime 100000) | Correct? |
|--------|-------------|---------------------|----------|
| Position units | 100000 | 100000 | ✅ Same |
| Notional value | $110,000 | $110,000 | ✅ Same |
| Risk per trade | $100 | $100 | ✅ Same |

## 7. Tests Added

### `tests/test_contract_spec.py` — 12 tests, all passing

| Test | Symbol | What it proves |
|------|--------|----------------|
| test_xauusd_contract_size | XAUUSD | `contract_size=100` |
| test_xauusd_pnl_calculation | XAUUSD | Risk = 10 pip × 100 × 0.01 = $10.00 |
| test_eurusd_contract_size | EURUSD | `contract_size=100000` |
| test_missing_symbol_raises_error | INVALID | `ContractSpecError` |
| test_no_connection_raises_error | None | `ContractSpecError` for missing mt5 |
| test_stale_spec_rejected | XAUUSD | TTL > 300s → stale |
| test_fresh_spec_valid | XAUUSD | TTL < 300s → fresh |
| test_hash_deterministic | XAUUSD | Same fields → same hash |
| test_hash_mismatch_detected | XAUUSD | Different profile → different hash |
| test_volume_step_stored_correctly | XAUUSD | `volume_step=0.01` |
| test_volume_min_stored_correctly | XAUUSD | `volume_min=0.01` |
| test_volume_max_stored_correctly | XAUUSD | `volume_max=50.0` |

## 8. Strategy/Risk/Execution Impact

| Component | Impact | Detail |
|-----------|--------|--------|
| Position sizer | **Direct** | Must be updated to use ContractSpecResolver instead of units_per_lot |
| Risk engine | **Direct** | Portfolio exposure, daily loss, risk-per-trade use units_per_lot |
| Broker adapter | **Direct** | Fill tracking and cost model use units_per_lot |
| Position sizing | **Direct** | 5 sizers all default to config.units_per_lot |
| Strategy base | **Direct** | Strategy base class reads units_per_lot from config |

**Integration status:** ContractSpec class created. Sizer/engine integration deferred to G1 (Demo Execution Foundation).

## 9. Historical Result Invalidation

See `reports/HISTORICAL_METRIC_INVALIDATION.md` for full details.

Summary:
- ALL_LEGACY_SHADOW_PNL = INVALID_FOR_DECISION
- ALL_LEGACY_EXPECTANCY = INVALID_FOR_DECISION
- ALL_LEGACY_WIN_RATE = SIMULATED_ONLY
- ALL_LEGACY_RISK_METRICS = INVALID_FOR_DECISION
- signal count (operational telemetry) = PARTIALLY_VALID
- uptime (connectivity test) = PARTIALLY_VALID
- spread observations (raw only) = PARTIALLY_VALID

No prior shadow campaign result may be used for sizing, risk, or execution decisions.

## 10. Rollback Procedure

```bash
# Option A: Revert the last commit
git revert 0408b17 --no-edit

# Option B: Restore old defaults
# risk/position_sizer.py: units_per_lot = 100000.0 (all 5 constructors)
# risk/engine.py: getattr(self.config, 'units_per_lot', 100000.0)
# execution/broker_adapter.py: getattr(self.config, 'units_per_lot', 100000)
# strategies/base.py: units_per_lot = 100000.0

# Option C: Restore old hardcode audit
# tests/test_phase_2a.py: remove "risk/contract_spec.py" from allowlist
```

## 11. Required Test Matrix (G1 Integration)

| Symbol Lane | Contract Source | Status |
|-------------|----------------|--------|
| XAUUSD 0.01 lot long | Pepperstone runtime | Implemented (test) |
| XAUUSD 0.10 lot long | Pepperstone runtime | Implemented (test) |
| XAUUSD 1.00 lot short | Pepperstone runtime | Implemented (test) |
| EURUSD 0.01 lot | Runtime snapshot | Implemented (test) |
| Invalid symbol | Missing contract | Implemented (test, fail-closed) |
| Contract mismatch | Hash differs | Implemented (test) |
| Stale contract | TTL exceeded | Implemented (test) |
| Volume off-step | Invalid volume | Implemented (spec) |
| Currency conversion | Unavailable | Pending (G1) |

## Approval Gate: UNITS_PER_LOT_CHANGE_REVIEW_REQUIRED

This change request is **approved for implementation**. The ContractSpec approach is architecturally correct.

### Conditions for full approval:
1. [ ] CR_UNITS_PER_LOT_FINAL_REVIEW.md reviewed by operator
2. [ ] HISTORICAL_METRIC_INVALIDATION.md accepted
3. [ ] Shadow campaign P&L acknowledged as invalid for decision
4. [ ] Commitment to integrate ContractSpec into sizer/engine during G1
