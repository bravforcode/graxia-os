# Phase 2 Report — Contract-Aware Sizing and Pre-Trade Risk Engine

## Scope
Phase 2A (Safety Preflight) + Phase 2B (Contract-Aware Sizing + Pre-Trade Risk)

## Commit / artifact hashes
- Phase 2 commit: `273d2dc` feat(quant_os): Phase 2 — contract-aware sizing + pre-trade risk engine
- Pre-Phase 2 baseline: `d152e57` fix(quant_os): MTF cursor prevents look-ahead leakage
- Tagged invalid baseline: `invalid-baseline-mtf-leak-suspected`

## Environment
- Python 3.12.10, Windows, pytest 8.4.2
- MT5 terminal: `C:\Program Files\MetaTrader 5\terminal64.exe` (not connected during tests)
- No live data, no live orders, no credentials touched

## Implemented changes

### Phase 2A — Safety Preflight

| File | Action | Purpose |
|------|--------|---------|
| `reports/PHASE_2A_HARDCODE_AUDIT.md` | Created | 58 findings across 6 categories |
| `data/manifests/XAUUSD_D1.manifest.json` | Created | SHA-256 checksum, timestamps, source |
| `data/manifests/XAUUSD_H1.manifest.json` | Created | SHA-256 checksum, timestamps, source |
| `data/manifests/XAUUSD_M15.manifest.json` | Created | SHA-256 checksum, timestamps, source |
| `risk/risk_policy.py` | Created | `RiskPolicy` frozen dataclass, bps-based |
| `core/exceptions.py` | Modified | Added `StrictMTFViolation` |
| `backtest/engine.py` | Modified | `strict_mtf` field + cursor check |

### Phase 2B — Contract-Aware Sizing + Risk

| File | Action | Purpose |
|------|--------|---------|
| `broker/__init__.py` | Created | Package exports |
| `broker/contract_spec.py` | Created | `ContractSpec` frozen dataclass + hash |
| `broker/contract_snapshot_store.py` | Created | Immutable JSON snapshot store |
| `broker/mt5_gateway.py` | Created | READ-ONLY MT5 wrapper, no order_send |
| `risk/kill_switch.py` | Rewritten | Persistent JSON-file kill switch |
| `risk/position_sizer_v2.py` | Created | Broker-native sizing (calc_profit/margin) |
| `risk/pre_trade_risk.py` | Created | Final risk gate with all limit checks |
| `risk/risk_ledger.py` | Created | JSON-file daily risk tracking |

## Test evidence

```
34 passed in 0.87s

Phase 2A (11 tests):
  test_dataset_manifests_exist PASSED
  test_manifest_checksum_matches PASSED
  test_manifest_timestamps_ordered PASSED
  test_manifest_not_synthetic PASSED
  test_manifest_timezone_utc PASSED
  test_manifest_source_known PASSED
  test_risk_policy_basis_points PASSED
  test_risk_policy_no_pct_field PASSED
  test_strict_mtf_blocks_static_fallback PASSED
  test_hardcode_audit_no_units_per_lot_in_production PASSED
  test_no_order_send_in_phase2 PASSED

Phase 2B (23 tests):
  test_contract_spec_validate_valid PASSED
  test_contract_spec_validate_zero_tick_value PASSED
  test_contract_spec_validate_volume_min_gt_max PASSED
  test_contract_spec_frozen PASSED
  test_contract_snapshot_store_save_load PASSED
  test_contract_snapshot_hash_deterministic PASSED
  test_sizer_valid_input PASSED
  test_sizer_zero_sl_rejects PASSED
  test_sizer_wrong_side_sl_rejects PASSED
  test_sizer_below_min_volume_rejects PASSED
  test_sizer_rounds_down_to_step PASSED
  test_sizer_risk_never_exceeds_budget PASSED
  test_pre_trade_check_daily_loss_blocks PASSED
  test_pre_trade_check_weekly_loss_blocks PASSED
  test_pre_trade_check_max_positions_blocks PASSED
  test_pre_trade_check_kill_switch_blocks PASSED
  test_kill_switch_activate_deactivate PASSED
  test_kill_switch_persists PASSED
  test_risk_ledger_daily_tracking PASSED
  test_no_order_send_in_broker PASSED
  test_no_order_send_in_risk PASSED
  test_golden_xauusd_sizing PASSED
  test_golden_eurusd_sizing PASSED
```

## Safety invariants verified

| Check | Result |
|-------|--------|
| No `order_send` in broker/ | PASS — only in assertion + comment |
| No `order_send` in risk/ | PASS — 0 matches |
| `risk_per_trade_pct` absent from RiskPolicy | PASS — AttributeError on access |
| `strict_mtf=True` blocks engine without cursor | PASS — StrictMTFViolation raised |
| All datasets have valid manifests | PASS — 3/3 with SHA-256 |
| Manifest checksums match CSVs | PASS — verified |
| ContractSpec validates on creation | PASS — 0 errors on valid spec |
| Volume rounds down to broker step | PASS — golden test |
| Kill switch persists across restart | PASS — file-based |
| Golden XAUUSD sizing correct | PASS |
| Golden EURUSD sizing correct | PASS |

## Hardcode audit summary

- **8 MUST_REMOVE_FROM_PRODUCTION**: `units_per_lot` in engine/config/risk, `pip_value` in engine, gold "100 oz" assumption in gold_bot
- **6 REQUIRES_MANUAL_REVIEW**: old position_sizer.py, old risk_engine.py, broker_adapter.py
- Legacy files retained for backward compatibility; new modules (`position_sizer_v2`, `pre_trade_risk`, `risk_policy`) are the replacement production path

## Risk policy semantics

```python
RiskPolicy(
    risk_per_trade_bps=10,        # 0.10% of equity
    max_daily_loss_bps=50,        # 0.50%
    max_weekly_loss_bps=150,      # 1.50%
    max_total_drawdown_bps=300,   # 3.00%
    max_open_positions=1,
    max_orders_per_day=3,
    require_stop_loss=True,
    require_contract_snapshot=True,
    require_order_check=True,
    fail_closed=True,
    strict_mtf=True,
)
```

Basis-point conversion: `risk_per_trade_fraction = bps / 10000`
- 10 bps = 0.0010 = 0.10%
- 50 bps = 0.0050 = 0.50%

## Known limitations

1. **No bid/ask execution model yet** — fills still use close price in backtest
2. **No historical spread model yet** — spread not modeled in backtest
3. **No slippage model yet** — only simple pip-based slippage in engine
4. **No cost stress matrix yet** — not run spread/slippage × 1.5/2.0/3.0 scenarios
5. **No claim of validated edge** — liquidity_sweep remains CANDIDATE_ONLY
6. **No shadow/demo readiness** — no MT5 live connection, no order lifecycle
7. **Legacy `units_per_lot`** still in old engine/config — old path not deleted, new path is the replacement
8. **MT5 gateway not tested live** — all MT5 calls mocked/unavailable in test environment
9. **margin estimate from order_calc_margin()** is per-order only — does not account for existing open positions

## Gate checklist

```
[✓] units_per_lot, 100000, fixed XAU assumptions absent from new production sizing path
[✓] Every sizing decision can be bound to immutable contract_snapshot_id
[✓] Config risk uses basis points only, no _pct ambiguity
[✓] symbol_info() is source of truth for symbol metadata (via mt5_gateway)
[✓] order_calc_profit() used for loss-at-stop calculation (via position_sizer_v2)
[✓] order_calc_margin() used for margin estimate (via position_sizer_v2)
[✓] order_check() is mandatory preflight (via pre_trade_risk)
[✓] Missing/invalid/stale contract data = reject + audit + fail closed
[✓] Volume rounding never causes risk above budget
[✓] Kill switch persistent and tested
[✓] Data manifest/checksum/UTC tests pass
[✓] Strict MTF mode has no static fallback
[✓] No order_send in Phase 2 code paths
[✓] 34/34 tests pass
[✓] Report issued with honest verdict
```

## Decision

**PASS_TO_PHASE_3**

Phase 2 infrastructure is in place. The new sizing and risk modules are built, tested, and verified safe (no order_send, no hardcoded contract assumptions, fail-closed design). However:

- The old engine/config still have legacy `units_per_lot` — this is technical debt, not a blocker for Phase 3
- MT5 gateway needs live validation in Phase 3B
- The backtest engine needs bid/ask execution model (Phase 3) before any P&L claim

## Next permitted phase

Phase 3 — Bid/ask execution + cost model + next-bar fill timing

## Explicitly prohibited actions

- Do NOT claim liquidity_sweep has a validated edge
- Do NOT claim the strategy is profitable or demo-ready
- Do NOT run live orders or connect to MT5 for execution
- Do NOT start EURUSD research (Phase 4)
- Do NOT optimize strategy parameters
- Do NOT start shadow mode (Phase 6)
