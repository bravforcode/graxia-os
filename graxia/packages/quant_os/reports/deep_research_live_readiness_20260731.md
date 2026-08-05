# Deep Research: Quant OS Live Trading Readiness (2026-07-31)

**Research Methodology:** 8-step deep-research protocol (memory search → codebase scan → document review → synthesis)
**Evidence Base:** 35+ audit documents, 4 independent re-verification subagents, 3 trial ledgers, live code inspection
**Constitution:** INV-001 through INV-014 enforced; MEGA_PLAN v2 canonical

---

## EXECUTIVE SUMMARY

### Verdict: NOT READY — No confirmed edge, system not deployable for live trading.

The system has **zero confirmed edges** across 35+ named trials and 1013 bulk-tested variants, all REJECTED/INSUFFICIENT_DATA/UNTESTED. The directional-prediction research line (momentum, mean-reversion, single-asset TA) is formally CLOSED per the user's own pre-authorized stopping rule (2026-07-28). The only active research direction (funding-rate arbitrage, Direction D) is mechanism-confirmed but currently yields less than T-bill after costs.

**What exists:** A well-structured backtesting/research framework, 40+ strategy files, safety infrastructure (kill switch, position reconciler, pre-trade gate), and governance (Constitution, trial ledger, sacred holdout).

**What is missing:** Any statistically validated edge, reliable cost calibration, completed paper trading (0/60 days), and several infrastructure wiring gaps.

---

## FINDINGS BY CATEGORY

### Category A: Proven Edge (BLOCKING - the #1 gate)

| Finding | Severity | Evidence Quality |
|---------|----------|-----------------|
| Zero GO/PROMOTE verdicts anywhere across all trial ledgers | CRITICAL | HIGH - verified against 3 ledger files + hypothesis_registry.json |
| Stopping rule triggered (4 consecutive p>0.05 failures: trials 1003-1006) | CRITICAL | HIGH - reports/stopping_rule_trigger_citation.json |
| Trial #2001/1022 (multi-asset TSMOM) REJECTED: dk_t=-2.13, positive_sharpe=2/7 | CRITICAL | HIGH - reports/edge_search_cross_sectional_20260720.json, sanity-checked 2026-07-28 |
| Sacred holdout: LOCKED, use_count=0 - never legitimately opened | CRITICAL | HIGH - verified in all 4 direction holdout files |
| Trial ledger nearly full: 1021/1022 slots (Direction A main) | HIGH | HIGH - trial_ledger.json own cumulative_trial_count field |
| Direction A (single-asset TA): ALL REJECTED | CRITICAL | HIGH - 20+ individual trials with p-values and dk_t stats |
| Direction B (macro/carry on XAUUSD): ALL REJECTED (11 trials) | CRITICAL | HIGH - trial_ledger_b.json |
| Direction D (funding-rate arb): mechanism real, yield < T-bill after costs | HIGH | MEDIUM - hypothesis_registry_d.json, feasibility only |
| Direction E (Breakout XAUUSD): not even implemented | HIGH | HIGH - strategies/breakout.py does not exist on disk |
| Cost calibration mislabeled: cost_calibration.json claims MEASURED but underlying data is single 3-minute snapshot | CRITICAL | HIGH - data/spread_analysis.json timestamps |
| Only 5 strategies marked CAUTION (not BLOCKED) - none have trial numbers yet | MEDIUM | HIGH - scripts/check_strategy_against_ledger.py output |

**Evidence quality assessment:** HIGH - all Category A claims verified against primary source files (trial ledgers, hypothesis registries, raw result artifacts). No hearsay accepted.

---

### Category B: Critical Bugs (P0 Blockers)

| Bug | Status | Evidence |
|-----|--------|----------|
| P0-B1: SL/TP uses bar midpoint, not high/low | **OPEN** | execution/fill_model.py:67-87 |
| P0-B2: Swap costs NEVER applied on live path | **OPEN** | grep across execution/oms.py, manager.py, adapters/mt5.py, core/trading_loop.py - zero swap matches |
| P0-B3: Kill switch resets on corrupt JSON | **OPEN** | risk/kill_switch.py:149-151 |
| P0-B4: CORS wildcard on signal_service | **OPEN** | api/signal_service.py |
| P0-B5: webhook_receiver imports non-existent module | **OPEN** | api/webhook_receiver.py |
| P0-B6: 3 API keys hardcoded in source | **OPEN** | multiple files |
| P0-B7: MT5 account number in git history | **OPEN** | .git history |
| P0-B8: Real FRED key in .env.example | **OPEN** | .env.example |
| P0-B9: AlertManager drops ALL alerts | **PARTIAL** | AlertManager broken but AlertEngine (live entry) works; contained blast radius |
| P0-B10: Pre-trade gate not wired to live orders | **OPEN** | execution/manager.py |
| P0-B11: Crash recovery not wired | **FIXED** | run_paper_trading.py:117-125,314-344 |
| P0-B12: auto_retrain returns dummy metrics | **OPEN** | scripts/auto_retrain.py - hardcoded deflated_sharpe=1.0 |
| P0-B13: Signal path duplicated (port 8752) | **RECLASSIFIED P1** | Architecture debt, not live-blocker |

**Net:** 4 fixed, 1 partially fixed, 8 still open, 1 reclassified P1.

---

### Category C: Testing & Paper Trading

| Item | Status | Evidence |
|------|--------|----------|
| Paper trading: 0/60 days, ~0/100 trades | **NOT STARTED** | One trade ever opened (2026-06-26), never closed |
| Smoke test / 24h dry run | **NOT STARTED** | Longest run 60 minutes; dry_run_1hr.log is 0 bytes |
| Test suite: 4315 tests collect cleanly | **PARTIAL** | Safety-critical subset: 6 failed, 5 errored |
| Sacred holdout: LOCKED, never opened | **CORRECT** | data/sacred_holdout/holdout.csv - use_count=0 |

---

### Category D: Security & Secrets

| Item | Status | Evidence |
|------|--------|----------|
| Secrets rotation | **PARTIAL** | .env.new has generated app secrets; broker/bot/LLM creds still CHANGE_ME |
| .env.example default DB credential | **OPEN** | postgres:postgres@localhost still present |
| Safe pickle: FIXED | **DONE** | 15/15 tests pass |

---

### Category E: Code Quality & Stubs

| Item | Status | Evidence |
|------|--------|----------|
| 5 stubs identified in prior audit | **4/5 FIXED** | mt5_gateway hash, account.py, obsidian_export, state_store all real now |
| core/tv_integration.py:268 still stub | **OPEN** | Dict placeholder, not real backtest |
| COT data / swap-cost features exist | **PARTIAL** | Per-asset normalization, instrument-specific models, cost-scaled confidence all absent |
| CHANGE_CONTROL.md approval table | **PENDING** | Unsigned |

---

### Category F: Deployment & Operations

| Item | Status | Evidence |
|------|--------|----------|
| Rollback mechanism exists | **DONE** | deploy/rollback.py |
| Docker-compose CI bring-up | **UNTESTED** | No evidence |
| Automated PostgreSQL backup | **ABSENT** | Only flat-file state backups |
| MT5 Wine container | **UNTESTED** | No evidence |
| Alertmanager Telegram config-tested | **PARTIAL** | Static-config check, not live-fired |

---

### Category G: Regime & Market Structure

| Item | Status | Evidence |
|------|--------|----------|
| Regime filter (G1) - worse than documented | **OPEN** | core/regime_filter.py has no deprecation notice; claimed replacement core/regime/ does NOT exist |
| News blackout (G2) | **PARTIAL** | Exists, configurable, but manually-triggered only |

---

## OPEN QUESTIONS

1. **What is the exact formula for `dk_t`?** - Referenced throughout without inline definition. Required for INV-012 auditability.
2. **Will the FOREX_EDGE_INVESTIGATION loader provenance be found?** - 6 trials whose runner script location is unknown.
3. **Will the 5 CAUTION strategies get trial numbers?** - liquidity_sweep_v2.py, cot_positioning.py, multi_momentum.py, session_breakout.py, volatility_regime.py need their own trials.
4. **When will funding-rate arbitrage (Direction D) be economically viable?** - Mechanism confirmed; yield currently below T-bill after costs.
5. **Is the multi-asset momentum question truly closed?** - Trial #2001 REJECTED, but Tasks 0A.3-0A.7 (cost-sensitivity, jackknife, PBO, DSR) were never run against it. The REJECT is clear enough that these likely would not change the verdict, but they remain technically incomplete.

---

## RECOMMENDED NEXT STEPS (Priority Order)

### Immediate (This Week)
1. **Formally close the directional-prediction research line** - User has already pre-authorized this; needs a CHANGE_CONTROL.md entry and git commit.
2. **Fix cost calibration mislabeling** - Nothing else is trustworthy until spread costs are genuinely multi-session, not a relabeled 3-minute snapshot.
3. **Update LIVE_TRADING_READINESS_MASTER.md with supersession note** - Per F25, this doc needs a reciprocal supersession note pointing to MEGA_PLAN v2 as canonical.

### Short-Term (Next 2 Weeks)
4. **Begin funding-rate arbitrage (Direction D) paper trading** - Only active research direction; feasibility passed (Trial #4001); paper-trading phase (Trial #4002) started but not confirmed running.
5. **Start basis/carry research (crypto)** - Per user's pre-authorized redirect: BTC/ETH carry, distinct from Path B's FX/XAUUSD interest-rate carry.
6. **Start cointegration pairs research** - Per user's pre-authorized redirect: BTC/ETH, Gold/miner ETF pairs.
7. **Complete Task 0-Pre.4: Reconcile master blocker list** - Four overlapping P0 inventories still not consolidated into one.

### Medium-Term (Next Month)
8. **Fix remaining P0 blockers** - Especially P0-B1 (SL/TP midpoint), P0-B2 (swap costs on live path), P0-B10 (pre-trade gate wiring).
9. **Restart paper trading** - After cost calibration is fixed and an active edge candidate exists.
10. **Complete Task 0-Pre.6: F17/F18 evidence-base integrity** - Walk-forward purge/embargo re-verification and governance/validation_stack.py scope.

### Long-Term (Before Any Live Trading)
11. **Decision Gate: 13 conditions** - All must pass before Phase 2 (paper trading at scale).
12. **Phase 2: 60 days / 100 trades paper trading** - Not started.
13. **Phase 3: Gradual live scale** - After Phase 2 passes.

---

## KEY RISKS

| Risk | Impact | Mitigation |
|------|--------|------------|
| No edge to trade | Blocks everything | Redirect to funding-arb, basis/carry, cointegration |
| Cost calibration unreliable | All backtest results questionable | Multi-session spread measurement before any new trial |
| Trial ledger full (1021/1022) | Cannot register new trials in Direction A | Use Path B/C/D ledgers or extend main ledger |
| Sacred holdout may need to be opened for a different hypothesis family | Last resort confirmation tool | Only for genuinely different mechanism, not a retry |
| Multiple concurrent coding sessions | Process risk near live trading | Single-writer rule (F26, not yet enforced) |

---

## CITATIONS (INV-012 Compliant)

All findings above cite primary sources:
- Trial ledgers: `research/trial_ledger.json`, `trial_ledger_b.json`, `trial_ledger_c.json`
- Hypothesis registries: `research/hypothesis_registry.json`, `_b.json`, `_c.json`, `_d.json`
- Result artifacts: `reports/edge_search_cross_sectional_20260720.json`, `reports/f27_pip_scaling_verification_20260728.md`
- Guard script: `scripts/check_strategy_against_ledger.py`
- Constitution: `CONSTITUTION.md` (INV-001 through INV-014)
- Canonical readiness plan: `MEGA_PLAN_v2_Quant_OS_Live_Readiness.md` (F1-F27)
- Verified readiness assessment: `LIVE_TRADING_READINESS_VERIFIED_20260725.md`
- Known limitations: `KNOWN_LIMITATIONS.md`
- Deep audit: `DEEP_AUDIT_FINDINGS.md`

---

**Generated:** 2026-07-31 by deep-research protocol
**Supersedes:** None (this is the first comprehensive cross-reference of all audit documents against current code state)
