# REPORT_G1_1_EXECUTION_FOUNDATION.md
## G1.1 — Execution Foundation & Canary Framework
**Verdict: PASS_TO_G2**
**commit:** `d150d09`
**Date:** 2026-06-23

## Provenance

| Field | Value |
|-------|-------|
| source_code_sha | `d150d09` |
| report_generation_sha | `d150d09` |
| generation_timestamp_utc | `2026-06-23T09:44:52Z` |
| contract_snapshot_hash | `968E3EB2DFBB268886655C17A65A6B8F4A1D1B5FACE5FC3A1558A5C5E0F1C2E4` |
| test_census_manifest | `artifacts/test_census/g1_1_manifest.json` |
| test_results | `artifacts/test_census/g1_1_results.txt` |

## G1.0 Corrections Summary

1. **Pips unsupported for XAUUSD/CFDs** — `ContractSpec.to_pips()` returns `None` for non-forex symbols. Tests confirm `test_xauusd_pips_unsupported` passes.
2. **Error magnitude fixed** — P&L calculation correctly uses `contract_size × price_delta` without scalar division. The 1,000,000× bug (dividing by tick_size) was eliminated. Tests confirm ±$10/±$100/±$1,000 for XAUUSD.
3. **Dead `units_per_lot` config removed** — `risk/position_sizer.py`, `risk/engine.py`, `execution/broker_adapter.py`, `strategies/base.py` no longer reference `units_per_lot`. All sizing uses `ContractSpec.contract_size`.
4. **All reports updated** — G1.0 report suite (6 reports) includes provenance fields, corrected wording, and evidence hygiene.

## G1.1 Execution Guards Created

| Guard | Module | Purpose |
|-------|--------|---------|
| DemoAccountGuard | `execution/demo_canary/demo_account_guard.py` | Rejects LIVE accounts |
| BrokerProfileGuard | `execution/demo_canary/broker_profile_guard.py` | Fingerprint hash verification |
| TerminalPathGuard | `execution/demo_canary/terminal_path_guard.py` | Pepperstone MT5 path enforcement |
| SymbolGuard | `execution/demo_canary/symbol_guard.py` | Only XAUUSD permitted |
| FeatureGate | `execution/demo_canary/feature_gate.py` | Execution disabled by default, toggleable |
| KillSwitch | `execution/demo_canary/kill_switch.py` | Global kill switch (persisted) |
| ExecutionMutex | `execution/demo_canary/execution_mutex.py` | Single-execution mutex (thread-safe) |

**Tests: 15/15 pass**

## Canary Model

### DemoCanaryPlan (`execution/demo_canary/canary_plan.py`)
- Immutable frozen dataclass
- Environment locked to `PEPPERSTONE_DEMO_ONLY`
- Symbol locked to `XAUUSD`
- Strategy hash must be `None` (generic first canary)
- Volume must be positive
- Deterministic `plan_hash` via canonical JSON SHA-256

### ApprovalPayload (`execution/demo_canary/approval_payload.py`)
- Frozen dataclass bound to one canary plan
- Contains: `canary_id`, `plan_hash`, nonce, environment, expiry
- No credentials, no raw account identity
- Nonce generated via `secrets.token_hex(32)`

### ApprovalVerifier (`execution/demo_canary/approval_verifier.py`)
- Verifies canary_id match, plan_hash match, environment is DEMO
- Rejects expired approvals
- Replay protection via used-nonce tracking

**Tests: 9/9 pass**

## State Machine — `CanaryStateMachine`

### States (22 states)
| State | Type | Description |
|-------|------|-------------|
| DRAFT | Initial | Plan created, no guards run |
| PROFILE_VERIFIED | Pre-submit | Broker profile fingerprint matched |
| CONTRACT_VERIFIED | Pre-submit | ContractSpec resolved |
| MARKET_DATA_VERIFIED | Pre-submit | Market data fresh |
| RISK_VERIFIED | Pre-submit | Risk checks passed |
| PREFLIGHT_PASSED | Pre-submit | Preflight checks passed |
| AWAITING_HUMAN_APPROVAL | Pre-submit | Sealed, waiting for operator |
| APPROVED | Pre-submit | Human operator approved |
| EXECUTION_MUTEX_HELD | Pre-submit | Mutex acquired, ready to submit |
| SUBMITTING | Post-submit | Order sent to broker |
| SUBMISSION_RECEIPT_RECORDED | Post-submit | Broker acknowledged |
| POSITION_RECONCILING | Post-submit | Reconciling position |
| POSITION_OPEN_CONFIRMED | Post-submit | Position verified open |
| EXIT_REQUESTED | Post-submit | Exit requested |
| EXIT_RECONCILING | Post-submit | Exit reconciling |
| CLOSED_CONFIRMED | Post-submit | Position closed confirmed |
| SEALED | Terminal | Lifecycle complete |
| REJECTED | Terminal/Blocked | Guard failure |
| EXPIRED | Terminal/Blocked | Approval TTL expired |
| KILLED | Terminal/Blocked | Killed by operator/system |
| SUBMISSION_UNKNOWN | Blocked | Broker state unknown |
| RECONCILIATION_FAILED | Blocked/Critical | Position mismatch |
| RECOVERY_REQUIRED | Terminal/Critical | Manual recovery needed |

### Allowed Transitions
Pre-submit states transition in strict sequential order:
`DRAFT → PROFILE_VERIFIED → CONTRACT_VERIFIED → MARKET_DATA_VERIFIED → RISK_VERIFIED → PREFLIGHT_PASSED → AWAITING_HUMAN_APPROVAL → APPROVED → EXECUTION_MUTEX_HELD → SUBMITTING`

Any state may transition to `REJECTED` on guard failure. `AWAITING_HUMAN_APPROVAL` may transition to `EXPIRED` on TTL.

### Actors
- `SYSTEM` — Automated guard/check transitions
- `OPERATOR` — Human approval/rejection
- `BROKER` — Broker acknowledgement (post-submit)

**Tests: 7/7 pass**

## Evidence Bundle

`execution/demo_canary/evidence_bundle.py` — `EvidenceBundle`
- Tamper-evident bundle for one canary lifecycle
- `add_artifact(name, data)` → SHA-256 hash
- `seal()` → manifest with `seal_hash` over all artifact hashes
- `verify()` → integrity check; returns `False` on tamper
- Artifacts stored in `output_dir/{canary_id}/`
- Manifest written as `00_manifest.json`

**Tests: 3/3 pass**

## Execution Isolation

### Order Submission Sole Allowlist
`execution/demo_canary/order_submission.py` is the ONLY file permitted to contain `order_send` logic.

### Broker Adapter Quarantine
`execution/broker_adapter.py` contains:
- Global `_submission_enabled = False` lock
- Line comments: `# QUARANTINED for G1.1. See order_submission.py for sole allowlist.`
- `MT5BrokerAdapter.place_order()` raises `RuntimeError` when `_submission_enabled` is `False`

### Import Isolation Tests
- `test_order_send_only_in_allowlist` — AST scan confirms zero `order_send` calls outside `order_submission.py`
- `test_broker_adapter_has_order_submission_disabled` — Verifies `order_submission.py` reference comment
- `test_submission_enabled_is_callable` — Verifies allowlist module exports `is_submission_enabled()`

**Tests: 3/3 pass**

## Test Census

| Suite | Collected | Passed | Failed |
|-------|-----------|--------|--------|
| execution_guards | 15 | 15 | 0 |
| canary_plan | 9 | 9 | 0 |
| state_machine | 7 | 7 | 0 |
| evidence_bundle | 3 | 3 | 0 |
| import_isolation | 3 | 3 | 0 |
| contract_spec | 25 | 25 | 0 |
| metric_invalidation | 10 | 10 | 0 |
| **Total** | **72** | **72** | **0** |

## Full Run Results

All 72 tests pass with 0 failures. Full verbose output at `artifacts/test_census/g1_1_results.txt`.

## G1.0 Contract Integration Tests (carried forward)

| Suite | Collected | Passed | Failed |
|-------|-----------|--------|--------|
| test_contract_spec.py | 25 | 25 | 0 |
| test_metric_invalidation.py | 10 | 10 | 0 |

ContractSpecResolver resolves with fail-closed semantics: missing/stale/mismatched → `ContractSpecError`.

## Verdict: PASS_TO_G2

All G1.1 requirements satisfied:
- [x] 7 execution guards with full test coverage
- [x] Immutable `DemoCanaryPlan` with deterministic hash
- [x] `ApprovalPayload` + `ApprovalVerifier` with replay protection
- [x] 22-state `CanaryStateMachine` with explicit transitions
- [x] Tamper-evident `EvidenceBundle`
- [x] Order submission isolation via AST-level `order_send` firewall
- [x] Broker adapter order_send calls quarantined behind global lock
- [x] G1.0 corrections (pip semantics, units_per_lot removal, magnitude fix, reports) verified
- [x] 72/72 tests pass, 0 failures, 0 skipped

**Next phase: G2 — Canary Execution Lifecycle**
