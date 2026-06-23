# REPORT_G3_2_1_TIME_AUTHORITY_FIX.md

## G3.2.1 — Time Authority and Dry-Run State Truth Fix

**Date:** 2026-06-23
**Branch:** `g0a-security-truth-closure-20260623`
**Commit:** `363c5f9`

---

## Verdict: READY_FOR_NEW_LOCAL_G3_REVIEW

---

## Root Cause

`symbol_info_tick().time` returns an MT5 server timestamp. When the server clock is ahead of the local Windows clock by ~3 hours, `time.time() - tick.time` produces a **negative** value (-10,799,112 ms).

The old freshness check:
```python
tick_fresh = tick_age_ms < 5000  # BUG: negative always passes
```

This is a **fail-closed violation**. A tick 3 hours in the future was labelled FRESH.

---

## Old vs New Freshness Predicate

| Condition | Old | New | Rationale |
|-----------|-----|-----|-----------|
| -10799112ms | ✅ FRESH (bug) | ❌ STALE | Negative = server clock ahead |
| -1ms | ✅ FRESH (bug) | ❌ STALE | Fail-closed: reject negative |
| 0ms | ✅ FRESH | ✅ FRESH | Exact match |
| 1000ms | ✅ FRESH | ✅ FRESH | Valid age |
| 5000ms | ❌ STALE | ❌ STALE | Boundary |
| 6000ms | ❌ STALE | ❌ STALE | Exceeds max |

```python
# OLD (broken): negative always passes
tick_fresh = tick_age_ms < 5000

# NEW (fail-closed): negative rejected
tick_fresh = 0 <= tick_age_ms < 5000
```

---

## Time Authority Architecture

| Source | Use | Authority? |
|--------|-----|------------|
| `symbol_info_tick().time` | Price input only | ❌ Not UTC authority |
| `symbol_info_tick().bid` / `.ask` | Execution price input | ✅ Price input |
| `copy_ticks_range()` | Timestamp authority | ✅ Canonical UTC tick source |
| `local_received_at_utc` | Receipt timestamp | ✅ Local UTC clock |

New fields added to plan:
```
tick_age_ms
time_authority_status (TIME_SOURCE_CONSISTENT | TIME_SOURCE_INCONSISTENT)
```

---

## State Machine Truth

| Mode | Before (bug) | After (fix) |
|------|-------------|-------------|
| Dry-run (pre-send) | `SUBMITTING` | `DRY_RUN_SEND_BLOCKED` |
| Real send | `SUBMITTING` | `SUBMITTING` |

`SUBMITTING` may only be entered immediately before a real `order_send` call. In dry-run mode, the state is `DRY_RUN_SEND_BLOCKED`. The state machine enforces `order_submission_count == 0` never pairs with `SUBMITTING`.

---

## Evidence: No Order Was Sent

| Check | Value |
|-------|-------|
| `order_send` called? | **NO** |
| `order_submission_count` | **0** |
| Positions before | **0** |
| Positions after | **0** |
| Orders before | **0** |
| Orders after | **0** |
| Feature gate after | **OFF** |
| Kill switch after | **ON** |
| Mutex after | **RELEASED** |
| State machine | `DRY_RUN_SEND_BLOCKED` |

---

## Test Results

### Test Manifest

| Suite | Command | Collected | Passed | Failed |
|-------|---------|-----------|--------|--------|
| Time authority | `python -m pytest tests/test_time_authority.py -v` | 18 | 18 | 0 |
| State machine | `python -m pytest tests/test_state_machine.py -v` | 7 | 7 | 0 |
| **Total** | | **25** | **25** | **0** |

### Test Coverage

| Test Class | Tests | What It Proves |
|-----------|-------|----------------|
| `TestTimeAuthority` | 9 | Negative age rejected, 0-age FRESH, stale rejected, ±3h/±7h blocked, TIME_SOURCE_* labels |
| `TestStateTruth` | 4 | Dry-run ≠ SUBMITTING, 0 orders ≠ SUBMITTING, recheck fail blocks |
| `TestQuoteTimeSeparation` | 2 | Price authority ≠ timestamp authority |
| `TestDryRunBlocked` | 3 | No order_send reachable, guards restored, artifact correct |

### Regression

All 7 existing `test_state_machine.py` tests pass, including the new `DRY_RUN_SEND_BLOCKED` transition from `EXECUTION_MUTEX_HELD`.

---

## Files Changed

| File | Change |
|------|--------|
| `scripts/g3_execute_demo_canary.py` | Fails-closed on negative tick age; TIME_SOURCE_* labels; DRY_RUN_SEND_BLOCKED state; dry_run_mode flag |
| `execution/demo_canary/enums.py` | Added `DRY_RUN_SEND_BLOCKED` enum state |
| `execution/demo_canary/state_machine.py` | Added EXECUTION_MUTEX_HELD → DRY_RUN_SEND_BLOCKED transition |
| `tests/test_time_authority.py` | 18 new tests (NEW) |

---

## Verdict: READY_FOR_NEW_LOCAL_G3_REVIEW

The P0 time-authority bug is fixed. The state machine tells the truth about dry-run mode. No order was sent.

### Next

Run fresh dry-run to verify:
1. `tick_age_ms` positive and within threshold
2. `time_authority_status` = `TIME_SOURCE_CONSISTENT`
3. State = `DRY_RUN_SEND_BLOCKED` (not `SUBMITTING`)
4. All guards pass

Then create new fresh plan for actual approval + one-shot `order_send`.
