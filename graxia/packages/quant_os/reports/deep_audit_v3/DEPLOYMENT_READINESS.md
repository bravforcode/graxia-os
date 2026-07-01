# PHASE 25 — DEPLOYMENT READINESS CHECKLIST
*Per R1–R18. Binary gate. YES requires evidence; NO and N/A stated explicitly.*

---

## Paper Trading Gate (must be YES before paper trading)

| # | Item | Status | Evidence |
|---|---|---|---|
| 1 | No active lookahead bias found (Phase 1 all PASS) | **PARTIAL** | audited paths clean (`engine.py:444`, `backtest_suite.py:25` `shift(1)`, `mtf_cursor.py`, `lookahead_guard.py`); **scaler-fit, `bfill`, `center=True`, DST UNVERIFIED** (Phase 1.4/1.6) |
| 2 | Independent feed cross-validation performed, no material discrepancy (Phase 2.2) | **NO** | `scripts/download_duka.py` exists; **no comparison result artifact anywhere** (Phase 2) |
| 3 | Cost model verified correct with units (Phase 3.2 confirmed) | **NO** | `cost_model.py:43` slippage≡spread (confirmed bug); `engine.py:726` 100× error for 5-digit FX majors (confirmed bug) |
| 4 | Same-bar SL/TP resolution confirmed conservative or tick-validated (Phase 4.1) | **YES** | `execution_simulator.py:287-303,354-367` resolves ADVERSE, flags `ambiguous_bar=true` (Phase 4) |
| 5 | At least one feature with IC > 0 out-of-sample with p < 0.05 (corrected) | **NO** | no corrected IC reported anywhere; only costed run = 67 trades, net negative (`SUMMARY.md`) |
| 6 | Backtest and live code confirmed to share feature computation logic (Phase 8) | **NO** | three separate code paths; backtest=`strategies/mtm,mrb,mlb`, live=`regime/` stack, suite=inline pandas (Phase 8) |
| 7 | MT5 crash recovery logic present (Phase 9.5) | **PARTIAL** | `execution/reconcile.py`, `recovery.py`, `canary/position_reconciler.py` exist; **call-site on boot UNVERIFIED** |
| 8 | No credentials in source code or git history (Phase 20) | **YES** | `git grep $(git rev-list --all)` empty; `.env` gitignored (Phase 20) |
| 9 | Basic logging of all trades present (Phase 21.1) | **YES** | structlog+Loki, tamper-evident `trade_ledger.py`, `data/paper_trade_log.csv` |
| 10 | Kill switch present in code AND persists across restart (Phase 9.2) | **PARTIAL** | persists to `data/kill_switch_state.json` ✓; **order-path `is_active()` gate UNVERIFIED** |
| 11 | Label-shuffling null test run, real result outside null distribution (Phase 13.1) | **NO** | test exists (`test_label_shuffling.py`); **never run / no result recorded → P0** |
| 12 | Broker execution model and real cost schedule match backtest (Phase 11.2) | **UNVERIFIED** | requires broker TOS + live spread history (Phase 11, Tier 2) |

**Paper Trading Gate: FAIL.** Items 2, 3, 5, 6, 11 are NO; 1, 7, 10, 12 are PARTIAL/UNVERIFIED. Only 4 items fully YES (4, 8, 9, and partially 10's persistence). **System must NOT paper-trade until at minimum items 3, 6, 11 are resolved.**

---

## Live Capital Gate (must be YES before real money)

| # | Item | Status |
|---|---|---|
| All Paper Trading Gate items YES | **NO** (5 NO, 4 PARTIAL) |
| OOS Sharpe > 0, p < 0.05 corrected, N_trades > 200 | **NO** (only costed run: 67 trades, net negative) |
| Realistic slippage modeled and still profitable | **NO** (slippage=spread bug; no profitable costed run) |
| All risk limits confirmed in code and tested (Phase 9.2) | **PARTIAL** (max_positions conflict 5 vs 1; consecutive-loss/balance-floor absent) |
| Alerting/monitoring active for silent failures (Phase 21.2) | **PARTIAL** (no disk/mem monitor; reconciliation trigger unverified) |
| Hypothesis log complete (Phase 17.1) | **UNVERIFIED** (Tier 3) |
| MT5 reconnect logic tested (Phase 9.3) | **YES** (`connection.py:103-114` exponential backoff) |
| Position reconciliation on restart confirmed (Phase 9.5) | **UNVERIFIED** |
| ForexFactory calendar integrated and tested | **PARTIAL** (`events/`, `news_events/` exist; join logic untraced) |
| Multiple-testing correction applied to all reported findings | **NO** (no corrected p-value anywhere) |
| DSR and PBO/CSCV computed and favorable post-correction | **NO** (modules exist, not run) |
| Capacity ceiling computed, capital within it (Phase 10.3) | **NO** (Tier 2, not done) |
| Kelly fraction derived with stated fraction rationale (Phase 10.2) | **NO** |
| Broker regulatory status, neg-balance protection, segregated funds (Phase 11.1) | **UNVERIFIED** (requires broker disclosure) |
| ≥1 tail-event stress replay performed, risk model survives (Phase 12.2) | **NO** (7-day data has no tail event) |
| Go/No-Go decision framework completed with explicit classification (Phase 24) | **NO** (Tier 2) |
| Adversarial stress tests all survived (Phase 13) | **NO** (none run) |
| ML model versioning + drift detection OR explicitly N/A (Phase 16) | **UNVERIFIED** (Tier 3) |
| Pre-committed live sequential stopping rule defined (Phase 22.2) | **NO** (Tier 3) |
| Operational runbook exists for non-developer operation (Phase 23.1) | **PARTIAL** (`reports/RUNBOOK.md` exists; completeness unverified) |

**Live Capital Gate: FAIL (hard).** The majority of items are NO or UNVERIFIED. **Under no circumstances should real capital be deployed on the current state.**

---

## Phase 25 — Verdict

**PAPER TRADING: NOT READY (5 hard NOs).**
**LIVE CAPITAL: NOT READY (overwhelming majority NO/UNVERIFIED).**

The system is at a "research/infrastructure-building" stage, not a "deployable trading system" stage. The infrastructure (kill switch persistence, reconciliation module, structured logging, adversarial-test stubs, MT5 reconnect) is genuinely built — but it has not been wired end-to-end against a confirmed edge, and several confirmed bugs (cost model, parity, unrun label-shuffle test) block even paper trading.
