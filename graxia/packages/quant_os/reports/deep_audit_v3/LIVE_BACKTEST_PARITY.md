# PHASE 8 — LIVE / BACKTEST PARITY AUDIT
*Per R9 (live vs backtest divergence must be checked explicitly).*

---

## 8.1 — Code Path Mapping

**There are at least THREE distinct execution code paths, not one shared path:**

| Path | Entry | Feature/Signal | Execution | Cost |
|---|---|---|---|---|
| A. Canonical backtest | `run_backtest.py` → `BacktestEngine` | strategies (MTM/MRB/MLB) via `generate_signal` | `BacktestExecutionSimulator` (next-bar open) | `execution/cost_model.py` |
| B. Research suite | `scripts/backtest_suite.py` | inline pandas (`close>ma` etc.) | **none** (bar returns) | **none** |
| C. Paper/live | `run_paper_trading.py` → `PaperTrader` | `RegimeDetector` + `SweepClassifier` + `EntryExecutor` | `PaperBroker` (simulated) / MT5 (live) | broker adapter |

**This is a P0 parity concern.** Path B (producing `results/*.json`) shares **nothing** with Path A or C — no shared feature function, no shared cost model, no shared execution logic. Path A (canonical backtest) and Path C (paper/live) use **different strategy/feature stacks entirely**: backtest uses `strategies/mtm.py`/`mrb.py`/`mlb.py`; live uses `regime/` (RegimeDetector, SweepClassifier, EntryExecutor). **There is no single shared feature-computation function used by both backtest and live.**

- `regime/sweep_classifier.py`, `regime/entry_executor.py` (the live signal path) are NOT called from `BacktestEngine`. Conversely `strategies/mtm.py` is NOT called from `run_paper_trading.py`. **What the backtest tests is not what the live system trades.**

## 8.2 — Feature Computation Parity

- Backtest: vectorial via `pandas_ta` or numba (`engine.py:571-673`).
- Live: `regime/` modules compute on rolling MT5 feed.
- **Mathematical equivalence test**: `tests/test_feature_parity.py` exists → a parity test exists. `[Not opened]` — whether it actually asserts live-path == backtest-path for the *same* strategy `[UNVERIFIED]`. Given the strategy stacks differ (8.1), a parity test between MTM and SweepClassifier would be meaningless. → **P0: confirm what `test_feature_parity.py` actually compares.**

## 8.3 — Signal Generation Parity

- Backtest threshold: per-strategy in `strategies/*.py`.
- Live threshold: `RiskOverlay`, `EntryExecutor` in `regime/`.
- Model weights: `ml/models/` artifact; loaded where `[UNVERIFIED]`.
- Sign convention: `core/enums.py` consistent. ✓ (the only parity-positive finding).

## 8.4 — Order Execution Parity

- Backtest: next-bar-open fill at bid/ask+slippage (`execution_simulator.py`).
- Live: `PaperBroker` (`execution/broker_adapter.py`) simulated; real MT5 via `mt5_connector` market orders.
- **Gap**: backtest assumes next-bar-open fill; live market order fills at current bid/ask. For M15/M1 the gap is small; for the 7-day M1 window, immaterial. But it is a systematic parity gap per protocol 8.4. → P2.

## 8.5 — Drift Detection

`ml/drift_monitor.py`, `core/drift_monitor.py` exist → drift monitoring *infrastructure* present. Whether it compares live signal stats vs backtest `[UNVERIFIED]`. → Phase 22 / P2.

## 8.6 — Shadow-Mode Parallel Validation

`shadow/` (42 entries), `run_shadow.py`, `scripts/shadow_service.py` exist → shadow-mode *infrastructure* is extensive. `shadow/broker_observed_runner.py`, `shadow/shadow_pipeline.py`. **Whether a shadow run has actually been executed and its signal-agreement rate computed against the backtest `[UNVERIFIED — no shadow result artifact found in reports/ or shadow_results/]`.** → P1 (the capability is built; the evidence of use is missing).

---

## Phase 8 — Verdict

**STATUS: FAIL (P0).** The single most dangerous finding in the audit so far:

**The backtest and the live/paper system do not share a strategy or feature code path.** Backtest exercises `strategies/mtm.py`/`mrb.py`/`mlb.py`; the live system runs `regime/` (liquidity-sweep pipeline). Additionally, `scripts/backtest_suite.py` (which produces the headline `results/*.json`) is a third path with no cost model and no execution simulation.

A backtest of strategy X tells you nothing about the live performance of strategy Y. **Every backtest number currently on disk is evidence about a strategy the live system does not trade, OR is an uncosted bar-return summary.** This invalidates any "validated by backtest" claim for the live paper-trading path until parity is established.
