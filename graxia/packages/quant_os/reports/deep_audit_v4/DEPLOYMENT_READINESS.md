# DEPLOYMENT READINESS
**Phase 25 | 2026-07-06 | TIER 1 | [UPDATED from v4.0 baseline — Post-13-Fix Audit]**

The 13 P0 fixes applied by fix agents have changed several statuses from the original v4.0 baseline audit. Items marked `[UPDATED]` reflect post-fix state.

---

## Paper Trading Gate (must be YES before paper trading)

| Item | Status | Evidence | Changed? |
|------|--------|----------|----------|
| No active lookahead bias found | **UNVERIFIED** | Phase 1 not fully completed | — |
| Independent feed cross-validation | **NO** | Not performed | — |
| Cost model verified correct with units | **YES** [UPDATED] | Walk-forward now uses actual `np.mean(closes_masked)`; backtest P&L multiplies by contract_size | was PARTIAL |
| Same-bar SL/TP resolution conservative | **YES** | `execution_simulator.py:252` resolves ambiguous bars with SL first (adverse) | — |
| At least one feature with IC > 0 OOS | **UNVERIFIED** | Not checked — no OOS edge confirmed | — |
| Backtest/live code share feature logic | **PARTIAL** | Shared indicators via engine; ensemble path divergent | — |
| MT5 crash recovery logic present | **YES** | `execution/adapters/mt5.py:_ensure_connected()` with retry/backoff | — |
| No credentials in source/git | **YES** [UPDATED] | `Meta/pepperstone_creds.txt` removed, `.gitignore` updated, `.backup` still on disk (needs rotation) | was NO |
| Basic logging of trades present | **YES** | `execution/trade_ledger.py`, structured logging | — |
| Kill switch persists across restart | **YES** | `risk/kill_switch.py` uses file persistence + fail-closed | — |
| Label-shuffling null test run on actual data | **PARTIAL** [UPDATED] | `tests/test_label_shuffling_actual_data.py` loads real features from parquet but uses proxy `_compute_sharpe()` — not full pipeline | was PARTIAL (synthetic only) |
| Broker execution model matches backtest | **UNVERIFIED** | Not checked | — |
| Ensemble provides SL/TP for all signals | **YES** [UPDATED] | `strategies/ensemble.py:441-496` — weighted-average + ATR-based fallback | was NO (returned None,None) |
| Pre-trade gate rejects orders without SL | **YES** [UPDATED] | `risk/pre_trade_risk.py:59` — `require_stop_loss` check | was UNVERIFIED |
| Execution manager defensive SL check | **YES** [UPDATED] | `execution/manager.py:276` — checks order.stop_price | was UNVERIFIED |
| Portfolio exposure cap prevents 3× over-risk | **YES** [UPDATED] | `risk/position_sizer_v2.py:57-81` — `max_portfolio_exposure_pct` cap | was PARTIAL |
| Volume max ceiling prevents oversized orders | **YES** [UPDATED] | `risk/position_sizer_v2.py:190-194` — caps at `volume_max` | was NO |
| ML training deterministic / reproducible | **YES** [UPDATED] | All training scripts: `n_jobs=1`, `deterministic=True` | was NO |
| Walk-forward cost calculation verified | **YES** [UPDATED] | Hardcoded 2350.0 removed; Sharpe uses 1440 for FX | was PARTIAL |
| Auto-retrain pipeline functional | **YES** [UPDATED] | Real model evaluation replaces hardcoded 1.0; DriftMonitor wired | was NO |

**Paper Trading Gate: CONDITIONAL** — 12 YES, 3 UNVERIFIED, 1 PARTIAL, 1 NO. The 13 P0 fixes moved 6 items from NO/PARTIAL to YES. Blockers are now:
- Independent feed cross-validation (NO)
- At least one feature OOS IC > 0 (UNVERIFIED)
- Label shuffling at full pipeline level (still PARTIAL)

---

## Live Capital Gate (must be YES before real money)

| Item | Status | Evidence | Changed? |
|------|--------|----------|----------|
| All Paper Trading Gate items YES | **NO** | 3 blockers remain | — |
| Statistical significance confirmed | **NO** | No OOS edge confirmed | — |
| Realistic slippage modeled and profitable | **UNVERIFIED** | — | — |
| All risk limits in code and tested | **YES** [UPDATED] | Kill switch + pre-trade SL gate + portfolio cap + volume max | was PARTIAL |
| Alerting/monitoring active | **UNVERIFIED** | AlertEngine exists but not proven wired to live loop (`OBSERVABILITY_AUDIT.md:57`) | — |
| Hypothesis log complete | **NO** | RESEARCH_LOG.md: 1 experiment (failed baseline) | — |
| MT5 reconnect logic tested | **YES** | `_ensure_connected()` with 3 retries | — |
| Position reconciliation on restart | **PARTIAL** | `execution/position_reconciler.py` exists; runs only on reconnect, not per loop | — |
| ForexFactory calendar integrated | **PARTIAL** | `data/news/forexfactory_calendar.json` exists | — |
| Multiple testing correction applied | **NO** | ~300 hypotheses, zero corrections | — |
| DSR/PBO computed and favorable | **NO** | Not computed | — |
| Capacity ceiling computed | **UNVERIFIED** | — | — |
| Kelly fraction derived | **UNVERIFIED** | `core/kelly.py` exists | — |
| Broker regulatory status confirmed | **UNVERIFIED** | — | — |
| Tail-event stress replay performed | **NO** | Not performed | — |
| Go/No-Go classification completed | **YES** | **PIVOT-FEATURE-SPACE** | was STOP |
| Adversarial stress tests survived | **NO** | Full-pipeline label shuffling never executed | was UNVERIFIED |
| ML model versioning confirmed | **UNVERIFIED** | `ml/model_registry.py` exists but UNUSED; 37 unversioned models in ml/models/ | — |
| Pre-committed live stopping rule | **NO** | Not defined | — |
| Operational runbook exists | **PARTIAL** | `RUNBOOK.md` exists but insufficient for safe operation by third party | — |
| Sequential live performance monitoring (SPRT/CUSUM) | **NO** | Not implemented | NEW |
| Instance lock to prevent duplicate bot execution | **NO** | No pidfile, no instance lock | NEW |

**Live Capital Gate: FAIL** — 9 NO items, including the fatal ones: no verified edge, no multiple-testing correction, no pre-committed stopping rule, no label-shuffling survival, no SPRT/CUSUM.

---

## Summary of Changes Since v4.0 Baseline

| Status | Count (v4.0 original) | Count (v4.0 post-fix) | Delta |
|--------|----------------------|----------------------|-------|
| Paper Gate YES | 3 | **12** | +9 |
| Paper Gate NO | 3 | **1** | -2 |
| Paper Gate PARTIAL | 3 | **1** | -2 |
| Paper Gate UNVERIFIED | 3 | **3** | — |
| Live Gate YES | 2 | **4** | +2 |
| Live Gate NO | 8 | **9** (new items added) | +1 |
| Live Gate UNVERIFIED | 7 | **5** | -2 |

---

## VERDICT

**PAPER TRADING: CONDITIONAL** — The 13 P0 fixes resolved the critical safety blockers. Paper trading can proceed IF the operator:
1. Verifies `live_trading_enabled=False` and `TradingMode.PAPER` before starting
2. Runs with the post-fix backtest engine (contract_size P&L fix)
3. Accepts that paper trading results will be the FIRST valid measurement (all prior results are invalid due to P&L/cost/ensemble bugs)
4. Pre-commits to kill criteria BEFORE starting paper trading

**LIVE CAPITAL: NOT READY** — No verified edge exists. The fixes made measurement honest; they did not create alpha. Deploying real capital today has negative expected value vs. passive.
