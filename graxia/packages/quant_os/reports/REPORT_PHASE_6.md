# Phase 6 — Shadow Trading

## Objective
Run complete production decision pipeline against live MT5 data, submit no broker orders.

## Pipeline Flow
MT5 ticks/bars → data health → event risk → strategy → MTF cursor → risk → contract sizing → simulated order intent → simulated fill/reconciliation → telemetry → alerts → NO order_send

## Files Created
- `shadow/__init__.py` — Module docstring
- `shadow/pipeline.py` — `ShadowPipeline`, `ShadowSignal`, `ShadowSession` with signal processing and session management
- `shadow/failure_rules.py` — 9 failure rules (`FailureRule` dataclass), all block progression (`blocks_progression=True`)
- `shadow/telemetry.py` — `ShadowTelemetry` with signal/event recording, `TelemetrySummary`, JSON export

## Shadow Failure Rules
All 9 rules defined in `failure_rules.py:10-20` — every rule has `blocks_progression=True`:

| Rule | Description |
|---|---|
| `STALE_DATA_ACCEPTED` | Stale data accepted into pipeline |
| `EVENT_BLOCK_BYPASS` | Order intent while event blocked |
| `MISSING_CONTRACT` | Missing contract snapshot accepted |
| `INVALID_SL_ACCEPTED` | Invalid SL accepted |
| `RISK_BREACH` | Risk budget breach |
| `DUPLICATE_IDEMPOTENCY` | Duplicate idempotency key |
| `INVALID_TRANSITION` | State machine invalid transition |
| `UNCORRELATED_ALERT` | Uncorrelated critical alert |
| `PIPELINE_EXCEPTION` | Unhandled exception in canonical pipeline |

`FailureRuleChecker` tracks violations and blocks progression when any rule is triggered.

## Pipeline Blocks (pipeline.py)
`ShadowPipeline.process_signal()` enforces 4 sequential blocks:
1. **Stale data** — pre-tagged stale signals pass through immediately (already rejected upstream)
2. **Event risk** — signals with `event_risk_state != "CLEAR"` → `REJECTED_EVENT_BLOCK`
3. **Market health** — signals with `market_health_state != "HEALTHY"` → `REJECTED_MARKET_HEALTH`
4. **Invalid SL** — signals with `stop_loss <= 0` → `REJECTED_INVALID_SL`

Signals passing all blocks → `ACCEPTED` (shadow only, no order submitted).

## Telemetry
- `ShadowTelemetry.start()` records session start
- `record_signal_created()` / `record_signal_accepted()` / `record_signal_rejected()` / `record_pipeline_error()`
- `get_summary()` → `TelemetrySummary` with total/accepted/rejected/error counts
- `export_json()` → full event log per session

## Exit Gate
- [ ] Continuous stable shadow period completed
- [ ] All signals auditable
- [ ] Market-health blocks work
- [ ] Event blocks work
- [ ] No execution function imported
- [ ] Real tick/spread data collected

## Test Results
No shadow-specific tests exist yet (`tests/test_shadow_*` not found).

| Component | Status | Notes |
|---|---|---|
| `shadow/__init__.py` | Implemented | Module docstring present |
| `shadow/pipeline.py` | Implemented | ShadowPipeline with session mgmt, 4-block signal processing, SHA-256 fingerprints |
| `shadow/failure_rules.py` | Implemented | 9 rules all blocking, FailureRuleChecker tracks violations |
| `shadow/telemetry.py` | Implemented | 4 event types, summary aggregation, JSON export |
| Test coverage | **MISSING** | No `test_shadow_*` tests found |

No execution function (`order_send`) is imported anywhere in the shadow module — verified.

## Verdict
**CONDITIONAL_PASS** — All shadow module files implemented with correct structure. No broker execution function is imported. Pipeline blocks, failure rules, telemetry, and session audit trail are in place. Blocked on: (1) no test coverage for shadow pipeline, (2) no evidence of live MT5 data flowing through the pipeline, (3) exit gate items unverified. Implement `tests/test_shadow_*.py` and run continuous shadow session before marking PASS.
