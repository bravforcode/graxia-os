# AUDIT_INDEX.md — Quant OS Deep Audit (v3 Protocol)

**Date:** 2026-06-29
**Auditor:** bridge agent (Ruflow/Gracia)
**Protocol:** QUANT_BOT_DEEP_AUDIT_PROMPT_v3.md (28 phases)

---

## TL;DR — Worst Finding First

**The backtest engine has a critical SL/TP detection bug that uses bar MIDPOINT instead of bar HIGH/LOW, systematically inflating win rate by failing to trigger stop-losses that would have been hit in reality. Combined with swap costs that are NEVER applied, every backtest result in this system overstates performance. The strategy already shows Net P&L = -$23.21 with the current (buggy) engine — real performance is worse.**

## Edge Status

`INSUFFICIENT EVIDENCE` — SUMMARY.md reports 58.2% OOS accuracy but Net P&L = -$23.21. With swap costs and correct SL/TP detection, the edge is almost certainly more negative. No edge found after costs.

## Go/No-Go Classification

`STOP` — Current approach (1min XAUUSD with XGBoost) does not survive real costs. Pivot to EURUSD/GBPUSD (tighter spreads) or higher timeframes (larger moves) recommended, but only after fixing the backtest bugs that make all current evidence unreliable.

## P0 Blocker Count: 8

1. **BUG-SL/TP**: SL/TP trigger uses bar midpoint, not high/low (`execution/fill_model.py:67-87`)
2. **BUG-SWAP**: Swap costs NEVER applied in backtest (`backtest/engine.py:125` defined but unused)
3. **BUG-KILL**: Kill switch silently resets to OFF on corrupt JSON (`risk/kill_switch.py:149-151`)
4. **BUG-PRETRADE**: Canonical pre-trade gate NOT wired to live orders (`execution/manager.py:115-116`)
5. **BUG-RECOVERY**: Crash recovery / position reconciliation NOT WIRED (`execution/recovery.py` dead code)
6. **SEC-KEYS**: 3 API keys hardcoded in source (`data_pipeline/config.py:20-22`)
7. **SEC-MT5**: MT5 account number in git history (7 commits, `scripts/export_mt5_historical.py:14`)
8. **SEC-ENV**: Real FRED key in `config/.env.example` (whitelisted from gitignore)

## Phase Status

| Phase | Status | Key Finding |
|-------|--------|-------------|
| 0 — Repo Census | PASS | 60+ directories, 200+ .py files, MT5 system |
| 1 — Data Pipeline | PARTIAL | Next-bar-open fills correct; fill model uses midpoint (BUG) |
| 2 — Data Integrity | N/A | No independent feed cross-validation performed |
| 3 — Math Correctness | FAIL | 9 bugs found, 6 inflate strategy metrics |
| 4 — Intrabar Fidelity | FAIL | SL/TP uses midpoint not high/low (R17 violation) |
| 5 — Feature Audit | PARTIAL | Only 3 experiments logged; no multiple testing correction |
| 6 — Statistical Rigor | FAIL | No label-shuffling test; no PBO/CSCV; no confidence intervals |
| 7 — Backtest Validation | FAIL | Swap not applied; cost model orphaned; Sortino inflated |
| 8 — Live/Backtest Parity | PARTIAL | Feature computation shared; fill model diverges |
| 9 — Risk & Execution | FAIL | Kill switch crash-unsafe; pre-trade gate not wired; recovery dead |
| 10 — Capital/Sizing | PARTIAL | Kelly correct; capacity ceiling not computed |
| 11 — Broker/Regulatory | UNVERIFIED | Pepperstone identified; regulatory status not confirmed |
| 12 — Tail Risk | UNVERIFIED | No stress-event replay performed |
| 13 — Adversarial | FAIL | No label-shuffling test run (P0 per protocol) |
| 14 — Alpha Combination | N/A | Single-strategy system |
| 15 — Portfolio | N/A | Standalone strategy |
| 16 — Model Lifecycle | PARTIAL | XGBoost used; no versioning; no drift detection |
| 17 — Research Methodology | FAIL | Only 3 experiments logged; no hypothesis log completeness |
| 18 — Code Quality | PARTIAL | Orphaned code (cost_model, slippage_model, swap_cost); duplicated logic |
| 19 — Determinism | UNVERIFIED | No reproducibility test run |
| 20 — Security | FAIL | 3 API keys hardcoded; MT5 account in git history; FRED key in .env.example |
| 21 — Observability | PARTIAL | structlog + prometheus present; no dead-man's switch wiring |
| 22 — Post-Deploy Monitoring | N/A | Not yet deployed live |
| 23 — Operational Continuity | FAIL | No runbook; crash recovery not wired |
| 24 — Opportunity Cost | STOP | No edge after costs; pivot recommended |
| 25 — Deployment Readiness | NOT READY | 8 P0 blockers |
| 26 — Honest Scorecard | FAIL | 18/25 questions answered NO or UNVERIFIED |
| 27 — Prioritized Next Steps | See below |

## Contradictions with Prior Audits

1. **SUMMARY.md says "Edge is REAL: 58.2% accuracy"** — This audit finds the edge is inflated by SL/TP midpoint bug and missing swap costs. The "real" edge is likely smaller or non-existent.
2. **STATUS.md says "Phase 3: 48/48 PASS"** — This audit finds the cost model from Phase 3 is orphaned (not wired to backtest engine), so the "passing" tests validated dead code.
3. **CONSTITUTION.md INV-008 claims "Kill switch persists across restart"** — This audit finds persistence is best-effort, not crash-safe (empty except block + non-atomic write).
4. **CONSTITUTION.md INV-009 claims "Pre-trade risk gate mandatory"** — This audit finds the canonical gate (`pre_trade_risk.py`) is dead code; live path uses legacy engine.

## Prioritized Next Steps

### P0 — Hard Blockers (must fix before ANY trading)

| # | Item | File:Line | Fix |
|---|------|-----------|-----|
| 1 | Fix SL/TP midpoint bug | `execution/fill_model.py:67-87` | Use `bar_low`/`bar_high` not midpoint |
| 2 | Wire swap costs into backtest | `backtest/engine.py:833-888` | Call `swap_cost.get_swap_cost_for_trade()` in `_close_position` |
| 3 | Fix kill switch crash safety | `risk/kill_switch.py:149-155` | Atomic write + fail-closed on parse error |
| 4 | Remove hardcoded API keys | `data_pipeline/config.py:20-22` | Fail closed if env var missing |
| 5 | Scrub MT5 account from git | `scripts/export_mt5_historical.py:14` | Remove + git filter-repo |
| 6 | Fix config/.env.example | `config/.env.example:1` | Replace real key with placeholder |
| 7 | Wire pre-trade gate to live | `execution/manager.py:115-116` | Call `pre_trade_check()` not legacy engine |
| 8 | Wire crash recovery on startup | `execution/manager.py` | Call `Recovery.on_startup()` on boot |

### P1 — Paper Trading Blockers

| # | Item | File:Line | Fix |
|---|------|-----------|-----|
| 9 | Fix Sortino denominator | `backtest/metrics.py:278` | Use `len(returns)` not `len(downside)` |
| 10 | Fix CPCV Sharpe ddof | `core/cross_validation.py:358,450` | Use `ddof=1` |
| 11 | Fix CPCV Sharpe annualization | `core/cross_validation.py:359,451` | Make timeframe-aware |
| 12 | Fix walk-forward Sharpe aggregation | `backtest/walk_forward.py:213` | Concatenate OOS returns, don't average |
| 13 | Wire session-aware cost model | `backtest/engine.py:117` | Use `cost_model.get_backtest_cost()` not flat `spread_pips` |
| 14 | Wire multi-factor slippage | `backtest/engine.py:116` | Use `slippage_model.estimate()` not flat `slippage_pips` |
| 15 | Fix unrealized PnL closing costs | `backtest/engine.py:920-926` | Subtract spread+slippage from unrealized |
| 16 | Run label-shuffling test | N/A | New script: shuffle labels, rerun 100x |
| 17 | Implement emergency close-all | `monitoring/dead_mans_switch.py` | Add real MT5 close-all implementation |
| 18 | Add MT5 reconnect to connector | `mt5_connector/connection.py` | Add retry loop with backoff |

### P2 — Live Capital Blockers

| # | Item | Fix |
|---|------|-----|
| 19 | Confirm broker regulatory status | Check Pepperstone FCA/ASIC registration |
| 20 | Compute capacity ceiling | Run slippage scaling test (2x, 5x, 10x) |
| 21 | Run tail-event stress replay | Replay SNB/COVID/Brexit scenarios |
| 22 | Set pre-committed kill criteria | Define numeric stopping rule |
| 23 | Create operational runbook | Document start/stop/kill-switch procedure |
| 24 | Implement SPRT live monitoring | Sequential test for edge decay |

### P3 — Quality Improvements

| # | Item | Fix |
|---|------|-----|
| 25 | Complete hypothesis log | Log all past experiments |
| 26 | Add data versioning | Manifests with SHA-256 (INV-005) |
| 27 | Add input drift detection | PSI/KS-test on live features |
| 28 | Remove orphaned code | Delete or wire cost_model, slippage_model |
| 29 | Add Parquet export | For ML pipeline compatibility |
| 30 | Add circuit breaker | For API failure cascades |
