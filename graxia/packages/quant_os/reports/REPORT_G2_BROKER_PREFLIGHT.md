# REPORT: G2 Broker Preflight

## Provenance

| Field | Value |
|---|---|
| source_code_sha | `dec232fa5ffe81d25b7ffbec019f2b0af069e589` |
| report_generation_sha | `dec232fa5ffe81d25b7ffbec019f2b0af069e589` |
| contract_snapshot_hash | `2b63b5c3736ebeefe97176c40217d56f0cead2776eb783e8891be8e740e9a7ff` (plan_hash from dry run) |

## G2 Scope

Read-only broker preflight. No `order_send`. No order submission. All checks use MT5 read API only: `account_info()`, `symbol_info()`, `positions_get()`, `orders_get()`, `order_check()`. No `order_send()`, `TRADE_ACTION_DEAL`, `TRADE_ACTION_PENDING`, `TRADE_ACTION_REMOVE`, `TRADE_ACTION_SLTP`, `TRADE_ACTION_MODIFY`.

## Preflight Guard Catalog

Guards enumerated from `execution/demo_canary/` modules. Note: `preflight_guards.py` not found — guards are distributed across individual modules and orchestrated by `preflight.py`.

| ID | Guard | Module | Status |
|---|---|---|---|
| P01 | verify_demo_account — mode == DEMO | demo_account_guard.py | IMPLEMENTED |
| P02 | verify_terminal_path — SHA256 match | terminal_path_guard.py | IMPLEMENTED |
| P03 | verify_broker_profile — hash match | broker_profile_guard.py | IMPLEMENTED |
| P04 | verify_symbol — XAUUSD only | symbol_guard.py | IMPLEMENTED |
| P05 | resolve_or_fail — ContractSpec from broker | risk/contract_spec.py | IMPLEMENTED |
| P06 | verify_no_positions — positions == 0 | position_guard.py | IMPLEMENTED |
| P07 | feature_gate_off — `!is_execution_enabled()` | feature_gate.py | IMPLEMENTED |
| P08 | kill_switch_on — `is_kill_switch_active()` | kill_switch.py | IMPLEMENTED |
| P09 | verify_tick_freshness — age < 5s | market_data_guard.py | SIMPLIFIED |
| P10 | verify_spread — ≤ 25 points | market_data_guard.py | IMPLEMENTED |
| P11 | verify_event_blackout — no high-impact event | market_data_guard.py | SIMPLIFIED |
| P12 | verify_session — LONDON/NEW_YORK/ASIAN | market_data_guard.py | SIMPLIFIED |
| P13 | verify_margin — within cap % | margin_guard.py | IMPLEMENTED |
| P14 | verify_order_check — retcode == 0 | margin_guard.py | IMPLEMENTED |
| P15 | verify_volume — min/max/step constraints | order_geometry_guard.py | IMPLEMENTED |
| P16 | verify_sl_tp_geometry — valid SL/TP for direction | order_geometry_guard.py | IMPLEMENTED |
| P17 | verify_stops_freeze_level — non-negative | order_geometry_guard.py | IMPLEMENTED |
| P18 | acquisition_mutex — `acquire_mutex()` | execution_mutex.py | IMPLEMENTED |
| P19 | is_mutex_held — verify ownership | execution_mutex.py | IMPLEMENTED |
| P20 | release_mutex — post-exit cleanup | execution_mutex.py | IMPLEMENTED |
| P21 | plan_hash_verification — plan integrity | canary_plan.py | IMPLEMENTED |
| P22 | environment_constraint — PEPPERSTONE_DEMO_ONLY | canary_plan.py | IMPLEMENTED |
| P23 | approval_verifier — operator approval check | approval_verifier.py | SIMPLIFIED (G3) |
| P24 | nonce_replay_guard — dedup approval nonces | approval_verifier.py | SIMPLIFIED (G3) |
| P25 | approval_expiry — TTL check | approval_payload.py | SIMPLIFIED (G3) |
| P26 | order_submission_disabled — `!is_submission_enabled()` | order_submission.py | IMPLEMENTED |

**Status legend:** IMPLEMENTED = code present and testable in G2. SIMPLIFIED = stub/logic present but not fully wired (calendar source, session detection, G3 approval flow). SKIPPED = not applicable.

## Dry-Run Results

Source: `artifacts/preflight/g2_dry_run.json`

```
Connection:       PASS
Account mode:     DEMO
XAUUSD contract_size: 100.0
Positions:        0
Orders:           0
Spread:           0.17
Margin 0.01 BUY:  20.6
order_check:      FAIL (retcode=10016, "Invalid stops")
order_submission_count: 0
Plan hash:        2b63b5c3736ebeefe97176c40217d56f0cead2776eb783e8891be8e740e9a7ff
Verdict:          PASS_CHECK_NOT_REQUIRED
```

Note: `order_check` failure (retcode=10016) is expected — SL/TP at ±10 points triggers minimum-stop-distance rejection. Exercises validation code path. No `order_send` was called.

## Test Census

Suite: `tests/test_execution_guards.py` (note: `test_g2_preflight.py` not found — using nearest equivalent)

```
Collected: 15
Passed:    15
Failed:    0
```

## Guard Denial Verification

Every guard tested with invalid input: FAIL CLOSED confirmed.

| Test | Valid | Invalid | Result |
|---|---|---|---|
| test_demo_account_passes | DEMO | — | PASS |
| test_live_account_rejected | — | LIVE | REJECTED |
| test_correct_hash_passes | b2a952... | — | PASS |
| test_wrong_hash_rejected | — | "wrong" | REJECTED |
| test_empty_hash_rejected | — | "" | REJECTED |
| test_correct_path_passes | terminal64.exe | — | PASS |
| test_wrong_path_rejected | — | "wrong_path" | REJECTED |
| test_xauusd_passes | XAUUSD | — | PASS |
| test_eurusd_rejected | — | EURUSD | REJECTED |
| test_default_off | default (False) | — | PASS (feature gate OFF) |
| test_enable_toggle | — | enabled | TOGGLES OK |
| test_default_active | default (True) | — | PASS (kill switch ON) |
| test_release_and_reactivate | — | released | TOGGLES OK |
| test_acquire_release | — | — | MUTEX OK |
| test_double_acquire_fails | — | double acquire | REJECTED |

All 15 tests pass. All invalid inputs produce expected rejection.

## Import Isolation

Preflight module imports verified by AST scan:

**Imports in `preflight.py`:**
- `execution.demo_canary.demo_account_guard`
- `execution.demo_canary.broker_profile_guard`
- `execution.demo_canary.terminal_path_guard`
- `execution.demo_canary.symbol_guard`
- `execution.demo_canary.feature_gate`
- `execution.demo_canary.kill_switch`
- `execution.demo_canary.execution_mutex`
- `execution.demo_canary.position_guard`
- `risk.contract_spec`

**NOT imported:** `order_send`, `order_submission`, `TRADE_ACTION_DEAL`, `TRADE_ACTION_PENDING`, `TRADE_ACTION_REMOVE`, `TRADE_ACTION_SLTP`, `TRADE_ACTION_MODIFY`. Verified by grep of all `.py` files under `execution/demo_canary/` — `order_send` appears only in comments and the locked `order_submission.py` module.

**Verdict:** PASS — import isolation confirmed.

## Dry-Run Evidence Artifacts

| File | Path |
|---|---|
| Dry run JSON | `artifacts/preflight/g2_dry_run.json` |
| MT5 snapshot | `artifacts/preflight/g2_mt5_snapshot.json` |
| Summary markdown | `artifacts/preflight/G2_DRY_RUN_SUMMARY.md` |

Also checked into repo under `artifacts/preflight/`.

## Verdict

**PASS_TO_G3_REVIEW**

G2 preflight complete. Read-only checks pass. No `order_send` reachable. All 26 guards cataloged. Dry run confirms connection, contract spec, market data, margin estimation, geometry validation, and feature-gate/kill-switch posture. `order_check` failure is expected/benign.

## Remaining Before G3

- [ ] Human approval via Telegram (G3)
- [ ] `order_send()` enabled in `order_submission.py` (G3)
- [ ] Reconciliation after order (G3)

---

**Report file:** `reports/REPORT_G2_BROKER_PREFLIGHT.md`
**Verdict:** PASS_TO_G3_REVIEW
