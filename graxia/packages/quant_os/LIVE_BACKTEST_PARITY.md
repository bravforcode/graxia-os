# LIVE_BACKTEST_PARITY.md — Phase 8

## 8.1 — Code Path Mapping

- **Feature computation**: `ml/pipeline.py::FeatureEngineer.generate_features()` used by both backtest and live scripts. **PASS — single implementation.**
- **Signal generation**: `alpha/engine.py::StrategyRouter` routes to strategies. Same code path for backtest and live. **PASS**
- **Execution**: DIVERGES — backtest uses `backtest/engine.py` (simulated), live uses `core/trading_loop.py` → `execution/oms.py` → `execution/adapters/mt5.py`. **Expected divergence.**

## 8.2 — Feature Computation Parity

- Backtest computes features vectorially on full dataset (`backtest/engine.py:734-805`)
- Live computes features on rolling basis (`ml/pipeline.py` called per-bar in `scripts/tsm_paper_trade.py`)
- **Test exists**: `tests/test_feature_parity.py` — verifies feature values match between vectorized and rolling paths. **PASS**

## 8.3 — Signal Generation Parity

- `alpha/engine.py` is shared between backtest and live. Same strategy weights, same ensemble logic.
- Model weights loaded from same `ml/models/` directory. **PASS**

## 8.4 — Order Execution Realism

- **Backtest**: Fill at estimated bid/ask from bar OHLC via `execution/execution_simulator.py`
- **Live**: Market order via `mt5.order_send()` — fills at real bid/ask
- **Parity gap**: Backtest estimates fill price; live gets real fill. Acceptable for initial validation. **P3**

## 8.5 — Drift Detection

- `ml/pipeline.py::DriftDetector` exists but is **ORPHANED** — not wired into live execution path
- No mechanism to detect when live signal statistics diverge from backtest expectations
- **P1 FINDING**: Backtest and live system can silently drift apart with no detection.

## 8.6 — Shadow-Mode Parallel Validation

- `shadow/` directory contains `shadow_pipeline.py`, `broker_observed_runner.py`, `pepperstone_campaign.py`
- Shadow mode IS implemented and has been exercised (tests exist: `test_shadow_isolation.py`, `test_shadow_pipeline.py`)
- Shadow mode runs read-only — no `order_send` (enforced by AST checks and runtime firewall tests)
- **PASS** — shadow mode exists and is properly isolated

## 8.7 — Independent Execution-Path Validation Engine

- NautilusTrader was evaluated but not integrated (no MT5 adapter)
- Only one backtest engine exists (`backtest/engine.py`). No second independent implementation.
- **Every parity check confirms internal self-consistency only — cannot rule out shared systematic errors.**
- **Scope limitation acknowledged.**

---

**P0 Findings**: 0
**P1 Findings**: 1 (drift detection orphaned)
**P2 Findings**: 0
**P3 Findings**: 1 (backtest/live fill price parity gap)
