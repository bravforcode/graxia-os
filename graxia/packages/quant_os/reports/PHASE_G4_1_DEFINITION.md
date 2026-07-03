# G4.1 Phase Definition — Live Production Hardening

**G track so far:** G0A ✅ → G0B ✅ → G1.0 ✅ → G1.1 ✅ → G2 ✅ → G2.1 ✅ → G2.1B ✅ → G2.1C ✅ → G3 ✅ → G3.2.4 ✅ → G3.3 ✅ → G3.4 ✅ → G4.0 ✅

**Current state:** 163 live demo orders executed, $49,980 balance, 459K ticks / 3 symbols, all safety gates verified. Tools: `mega_collect.py`, `spread_heatmap.py`, scheduler, dashboard, ML model.

---

## 1. Continuous Canary

**Goal:** Replace manual canary triggers with automated daily run cycles managed by the scheduler. Each cycle executes a full demo order pass, records results, and alerts on anomalies — no human-in-the-loop for standard passes.

**Acceptance criteria:**
- Scheduler invokes `DemoCanaryRunner.run_cycle()` at configurable interval (default: daily 09:00 UTC)
- Each run produces a `CanaryRunResult` persisted to `artifacts/canary_runs/` with timestamp, status, order count, P&L
- Alert (Telegram + log) on any failure: rejected order, broker disconnect, drawdown > threshold
- Weekly summary report auto-generated in `reports/canary_weekly/`
- Scheduler health-check endpoint surfaces last-run timestamp and next-run ETA

**Files to modify:**
- `canary/demo_canary_runner.py` — add scheduler integration hooks
- `canary/config.py` — add scheduler interval, alert threshold config
- `canary/demo_canary_config.py` — extend config dataclass for scheduling
- `canary/demo_policy.py` — verify policy permits automated runs
- `canary/demo_preflight.py` — add preflight checks for auto-run readiness
- `canary/weekly_report.py` — wire weekly summary generation
- `tests/test_demo_canary_runner.py` — add scheduled-run test cases

**Test commands:**
```powershell
python -m pytest graxia/packages/quant_os/canary/test_demo_canary_runner.py -v -k "schedule"
python -m pytest graxia/packages/quant_os/canary/test_weekly_report.py -v
python -m pytest graxia/packages/quant_os/tests/test_phase_10_micro_live.py -q
```

**Estimated effort:** M (3–4 days for scheduler integration + alert wiring + test coverage)

---

## 2. Position Lifecycle Audit

**Goal:** Every order's full lifecycle (open → fill → close → P&L) is tracked, persisted, and queryable. Detect orphaned positions, unmatched fills, and P&L discrepancies against broker statements.

**Acceptance criteria:**
- `OrderLifecycle` captures every state transition: `PENDING → SUBMITTED → FILLED → CLOSING → CLOSED → SETTLED`
- Each transition records: timestamp, broker_order_id, price, volume, P&L delta, reason
- `PositionReconciler` compares local lifecycle records against broker account history daily
- Reconciliation mismatches (ghost positions, missing fills, P&L drift > $1) raise alerts
- Full lifecycle export available as CSV in `artifacts/lifecycle_audit/`
- Dashboard panel shows active positions with age, P&L, time-in-market

**Files to modify:**
- `canary/order_lifecycle.py` — add P&L tracking, position-level state, CSV export
- `canary/position_reconciler.py` — extend reconciliation logic, add drift detection
- `canary/demo_canary_runner.py` — wire lifecycle recording into run cycle
- `core/dashboard.py` — add lifecycle panel data feed
- `canary/config.py` — add reconciliation window config
- `tests/test_order_lifecycle.py` — add P&L tracking and reconciliation tests

**Test commands:**
```powershell
python -m pytest graxia/packages/quant_os/canary/test_order_lifecycle.py -v -k "reconcile or pnl"
python -m pytest graxia/packages/quant_os/tests/test_phase_10_micro_live.py -q
```

**Estimated effort:** M (3–5 days for lifecycle extension + reconciliation + dashboard)

---

## 3. Slippage Model Integration

**Goal:** Replace static pip-based slippage with dynamic deviation predictions from the trained ML model (`slippage_model.pkl`). The model consumes real-time spread, volatility, and liquidity features; the execution engine applies model output per-symbol per-order.

**Acceptance criteria:**
- `train_slippage_model.py` produces a validated model artifact at `models/slippage_model.pkl`
- Execution pipeline loads model at startup, falls back to static slippage if model fails
- Model prediction informs `max_slippage` in each `order_send` call
- Slippage accuracy tracked: predicted vs actual deviation logged per order
- Dashboard panel shows slippage model accuracy (MAE, bias) over rolling 24h window
- Model retraining trigger: accuracy drops below 80% or 1,000 new samples collected

**Files to modify:**
- `scripts/train_slippage_model.py` — finalize pipeline, add validation holdout, auto-retrain trigger
- `execution/` — integrate slippage model into order building & execution flow
- `canary/demo_canary_runner.py` — pass model predictions to order guard
- `canary/demo_order_guard.py` — accept dynamic slippage from model
- `core/dashboard.py` — add model accuracy panel
- `canary/config.py` — add model path, fallback threshold, retrain config
- `tests/` — add model loading and prediction tests

**Test commands:**
```powershell
python scripts/train_slippage_model.py --validate
python -m pytest graxia/packages/quant_os/canary/test_demo_order_guard.py -v -k "slippage"
python -m pytest graxia/packages/quant_os/tests/test_be_p4_integration.py -v
```

**Estimated effort:** M (3–4 days for model integration + fallback + dashboard)

---

## 4. Spread-Based Scheduling

**Goal:** Skip order placement when spreads exceed per-symbol thresholds derived from the `spread_heatmap.py` historical analysis. Orders are held until spread tightens or cancelled after a timeout.

**Acceptance criteria:**
- `spread_heatmap.py` output feeds a symbol→threshold map (e.g., XAUUSD ≤ 0.35, EURUSD ≤ 0.15, GBPUSD ≤ 0.18)
- Preflight check compares live spread against threshold before every `order_send`
- Orders blocked by spread go to a PENDING_SPREAD state with a TTL (default: 120s)
- If TTL expires without spread improvement, order is cancelled and logged as `SPREAD_REJECTED`
- Dashboard shows live spread vs threshold per symbol with block/count stats
- Scheduler respects spread windows: orders placed only in historically tight hours

**Files to modify:**
- `scripts/spread_heatmap.py` — export threshold config, add per-symbol summary
- `canary/demo_preflight.py` — add spread check before order guard
- `canary/demo_order_guard.py` — add PENDING_SPREAD state handling
- `canary/order_lifecycle.py` — add SPREAD_REJECTED transition
- `canary/config.py` — add spread thresholds, TTL, window config
- `core/dashboard.py` — add spread status panel
- `tests/test_demo_preflight.py` — add spread-gate test cases

**Test commands:**
```powershell
python scripts/spread_heatmap.py --export-thresholds
python -m pytest graxia/packages/quant_os/canary/test_demo_preflight.py -v -k "spread"
python -m pytest graxia/packages/quant_os/canary/test_demo_order_guard.py -v -k "pending_spread"
```

**Estimated effort:** S–M (2–3 days for threshold derivation + preflight + dashboard)

---

## 5. Multi-Symbol Expansion

**Goal:** Expand from current 3 symbols (XAUUSD, EURUSD, GBPUSD) to 8+ symbols systematically, with per-symbol preflight, risk, and lifecycle support.

**Acceptance criteria:**
- Target symbols defined: XAUUSD, EURUSD, GBPUSD, USDJPY, AUDUSD, USDCAD, NZDUSD, USDCHF
- Each symbol has a declared spread threshold, max position size, and volatility class
- `mega_collect.py` collects all 8 symbols concurrently
- `DemoPreflight` validates every symbol independently before any order
- Risk engine caps total exposure across all symbols (portfolio margin check)
- Backfill historical data for new symbols (min 30 days)
- Dashboard shows per-symbol P&L, volume, order count, and live status
- Regression: G2.1 geometry, G2.1B side-correctness, G3.3 audit all pass with new symbols

**Files to modify:**
- `canary/config.py` — add symbol registry with per-symbol parameters
- `canary/demo_preflight.py` — symbol-agnostic preflight, portfolio margin check
- `scripts/mega_collect.py` — extend symbol list, add concurrent symbol collection
- `canary/demo_canary_runner.py` — multi-symbol run cycle
- `core/dashboard.py` — multi-symbol P&L and status panels
- `canary/risk/` — or existing risk module — portfolio-level exposure calc
- `tests/` — per-symbol validation and portfolio risk tests

**Test commands:**
```powershell
python scripts/mega_collect.py --symbols XAUUSD,EURUSD,GBPUSD,USDJPY,AUDUSD,USDCAD,NZDUSD,USDCHF --ticks 5000
python -m pytest graxia/packages/quant_os/canary/test_demo_preflight.py -v -k "multi_symbol"
python -m pytest graxia/packages/quant_os/tests/ -q --tb=short
```

**Estimated effort:** L–XL (5–8 days for symbol expansion + risk calc + full regression)

---

## Rollback / Fallback Plan

| Component | Failure scenario | Mitigation |
|---|---|---|
| Continuous Canary | Scheduler crash | Manual `run_cycle()` via CLI; fallback to G4.0 manual trigger |
| Position Lifecycle | Reconciliation alert storm | Disable auto-reconciliation, revert to G4.0 order-only tracking |
| Slippage Model | Model prediction error > 100% | Auto-fallback to static pip-based slippage (config flag) |
| Spread Scheduling | Spread threshold too tight, no orders | Auto-widen threshold 10% per hour until orders pass |
| Multi-Symbol | New symbol broker rejection | Remove symbol from registry, continue with remaining set |

---

## Phase Summary

| Item | Est. Effort | Risk | Dependencies |
|---|---|---|---|
| 1. Continuous Canary | M | Low | Scheduler infra exists |
| 2. Position Lifecycle Audit | M | Low | OrderLifecycle exists |
| 3. Slippage Model Integration | M | Medium | Model trained, needs integration |
| 4. Spread-Based Scheduling | S–M | Low | spread_heatmap.py exists |
| 5. Multi-Symbol Expansion | L–XL | Medium | All prior items |

**Total estimated effort:** 16–23 days

**Gate check:** All 5 items must pass acceptance criteria before G5 planning begins.

---

*Generated: 2026-06-24 | Track: G4.1 | Status: DEFINED*
