# Live Trading Readiness — Verified Against Current Code (2026-07-25)

**Method:** 4 independent subagents re-checked every claim in `LIVE_TRADING_READINESS_MASTER.md` (dated 2026-07-12) against current file content, ran real tests where possible, and cited file:line for everything. No claim below was accepted from the old doc without re-verification — the errata-correction work earlier today already found one prior audit doc (`MEGA_PLAN_v3_ERRATA_20260722.md`) contained a materially wrong diagnosis, so nothing here is assumed true by default.

**Overall verdict: NOT READY.** Category A (proven edge) is the blocking gate and it fails outright — worse than the 07-12 doc implied in one respect (the one active new hypothesis, Breakout XAUUSD, isn't even implemented yet) and better in others (several Category B "critical bugs" turned out fixed or overstated). Profit-maximization is not yet a valid question to optimize — there is no confirmed edge to size or scale.

---

## Category A — Proven Edge (BLOCKING — nothing else matters without this)

- **Zero GO/PROMOTE verdicts anywhere.** Across `trial_ledger.json`, `trial_ledger_b.json`, `trial_ledger_c.json`, `hypothesis_registry.json` (+`_b`/`_c`): ~35+ named trials plus 1013 bulk-tested variants, all REJECTED / INSUFFICIENT_DATA / UNTESTED. Sacred holdout files show `use_count: 0, status: LOCKED` in every direction — the one test that could confirm surviving edge has never been legitimately opened.
- **CONSTITUTION.md's stopping-rule claim is stale/wrong.** It asserts "STOPPING RULE TRIGGERED" (2026-07-13), but live counters in `trial_ledger.json` show consecutive-failure counts reset to 0, and research continued past the trigger (trials 2007–2008 exist after Path B hit its 3-fail threshold). Main ledger is nearly at its cap: 1021/1022 slots used.
- **Trial #1028 (Breakout XAUUSD H1) — the one hope — is pre-registered only.** `strategies/breakout.py` does not exist on disk. Never run.
- **Cost calibration data is mislabeled.** `config/cost_calibration.json` claims `status: MEASURED` over a "2026-07-03 to 2026-07-05" window (implying multi-day). The underlying raw file, `data/spread_analysis.json`, shows the actual XAUUSD measurement is a single ~3-minute snapshot (05:48:07–05:51:17 on 07-03). Every backtest that trusted this calibration inherited an under-sampled, session-blind cost model.

**What this means:** there is currently no active, running path toward a confirmed edge. Path B and Direction C are exhausted (rejected). Direction A's only live candidate (breakout) hasn't been coded. This is the actual #1 priority — ahead of any infra/security work.

## Category B — Critical Bugs (12 items re-verified)

| # | Item | Verdict | Evidence |
|---|---|---|---|
| 1 | `position_reconciler.py` not wired | **FIXED** | `run_paper_trading.py:117-125,314-344` instantiates + calls `.reconcile()` every 100 cycles, alerts on drift. Doc's "not wired" text was a stale docstring. |
| 2 | `oms.py` exit_price="" placeholder | **Claim doesn't reproduce** | No `exit_price` field exists in current architecture; fills flow through `avg_fill_price` populated from broker (`oms.py:454`). |
| 3 | `manager.py` no stop-loss retry | **STILL OPEN** | `manager.py:310-312` hard-blocks and raises on missing stop_price; no retry path; no test. |
| 4 | `api/orders.py:72` placeholder | **STILL OPEN** (verbatim) | Line 75-77: returns `501 Not implemented — use webhook endpoint`. Possibly intentional (webhook is the real path) — needs a human call on whether this is a gap or a design choice. |
| 5 | `risk/position_sizer_v2.py:236` margin check placeholder | **STILL OPEN** (verbatim) | Comment: `ponytail: defer full margin check to pre_trade_risk`. Not verified whether `pre_trade_risk` actually performs it — open question, check before go-live. |
| 6 | `telegram_commands.py` pass blocks | **FIXED** | `/kill` and `/resume` have real confirm-flow logic; the one remaining `pass` is an unrelated exception handler. |
| 7 | `kill_switch.py` no auto-recovery | **FIXED** | `_load()` quarantines corrupted state files and fails closed to `ACTIVE` (blocks trading) rather than crashing — real recovery behavior. |
| 8 | `state_coordinator.py` 5-store sync untested | **PARTIALLY FIXED** | Real propagation logic exists, but no per-store try/except — one store's callback raising leaves the rest un-synced. Untested failure path confirmed still open. |
| 9 | `monitoring/alerts.py` "all alerts silently dropped" | **STILL OPEN but downgraded severity** | Confirmed verbatim: `send_alert()` just appends to a list and returns `True` for every severity. **But**: this class is not the production alert path. Live entry point (`run_paper_trading.py`) uses a separate, fully-implemented `AlertEngine` (real Telegram routing). The only caller of the broken class, `RealtimeReconciler`, is itself never instantiated outside tests. Real bug, contained blast radius — not "zero notifications on kill-switch trip" as originally claimed. |
| 10 | `heartbeat_monitor.py` vs `DeadMansSwitch` threshold mismatch | **STILL OPEN** | 1h/4h thresholds vs DMS's 5-min default, no shared config, no reconciling test. |
| 11 | `auto_retrain.py` dummy metrics | **STILL OPEN** | `evaluate_model()` ignores its input and returns hardcoded `ModelMetrics(deflated_sharpe=1.0, oos_max_drawdown=10.0)` for every call — champion/challenger comparison is not functional. |
| 12 | `ml/pipeline.py` missing seed | **Claim doesn't reproduce** | `random_state=42` set for XGBoost/LightGBM/RandomForest; time-series split uses `shuffle=False`. |

Net: 4 fixed, 1 partially fixed, 5 still open, 2 claims that don't match current code (stale doc, not evidence of anything wrong).

## Category C/D — Testing, Paper Trading, Security

- **Paper trading (Golden Rule #3, needs 60d/100 trades): STILL OPEN, badly.** One trade ever opened (XAUUSD long, 2026-06-26), never closed. Bot ran continuously for ~16h then stopped. Shadow-trade log path (`data/shadow_trades.jsonl`) was never created — zero signals persisted. A scheduled Jul-23 evaluation checkpoint file exists but is 0 bytes — evaluation never actually ran. **Effective progress: 0/60 days, ~0/100 trades.**
- **Smoke test / 24h dry run: STILL OPEN.** Longest confirmed run is 60 minutes (`reports/dry_run_analysis_20260629.md`). A log file literally named `dry_run_1hr.log` is 0 bytes.
- **Test suite: collection healthy, execution not all-green.** 4315 tests collect cleanly (confirmed independently). A real run of the safety-critical subset (kill-switch, chaos, safe_pickle — 1161 tests) produced **6 failed, 5 errored** — mostly test-code/environment issues (FastAPI test signature mismatches, TLS cert generation needing bash unavailable in this shell, one flaky rate-limit test), not proven safety-path defects, but "0 collection errors" from prior sessions should not be read as "suite is green."
- **Secrets rotation: UNKNOWN by design (human action) — but partial evidence found.** A `.env.new` draft exists with real generated app secrets (JWT/HMAC/API key) already filled in, but the primary broker/bot/LLM credentials are still `CHANGE_ME_*` placeholders. Rotation was started, not completed.
- **`.env.example` still has a default DB credential** (`postgres:postgres@localhost`) — the 07-12 doc flagged this as "must be removed"; it hasn't been.
- **`safe_pickle.py`: FIXED**, 15/15 tests pass including a real LightGBM round-trip — prior "not tested with all model formats" claim is stale.

## Category E/F/G — Code Quality, Deployment, Regime/News

- **E1 stubs:** 4 of 5 fixed (mt5_gateway hash, account.py, obsidian_export, state_store all have real implementations now). `core/tv_integration.py:268` is still a stub dict, not a real backtest.
- **E2:** COT data and swap-cost features exist; per-asset-class normalization pipeline, instrument-specific model training, and cost-scaled confidence threshold are all still absent or partial.
- **E3:** `CHANGE_CONTROL.md` approval table is explicitly `PENDING` — unsigned. Evidence-pack *infrastructure* exists (`validation/evidence_pack.py`) but that's not the same as an assembled, signed pack for any specific phase.
- **F1 deployment:** rollback mechanism exists (`deploy/rollback.py`). docker-compose has no CI/end-to-end bring-up evidence. No automated PostgreSQL backup (only flat-file state backups exist). MT5 Wine container untested.
- **F2 monitoring:** Alertmanager Telegram routing is config-tested (asserts a Telegram receiver exists) but that's a static-config check, not a live-fired-alert test.
- **G1 regime filter — worse than documented.** `core/regime_filter.py` has no deprecation notice (contradicts the 07-12 doc's claim it's deprecated). The claimed replacement package `core/regime/` **does not exist at all**. `scripts/edge_search_all.py` has zero regime references — walk-forward validation completely ignores regime, full stop.
- **G2 news blackout:** exists, configurable, but still purely manually-triggered — no live economic-calendar API wiring.

---

## What actually needs to happen next, in order

1. **Fix the cost-calibration mislabeling first.** Nothing else is trustworthy until spread costs are genuinely multi-day/multi-session, not a relabeled 3-minute snapshot. This affects every past REJECT verdict's credibility, not just future ones.
2. **Either implement `strategies/breakout.py` and run Trial #1028 for real, or acknowledge there is currently no active edge-discovery path.** Path B and Direction C are exhausted.
3. Do not treat "0 collection errors" as "tests pass" — get the safety-critical subset (kill-switch, chaos, reconciliation) to a real green before trusting it operationally.
4. Paper trading has not meaningfully started. Restarting it is pointless before #1 and #2 — there'd be nothing with a claimed edge to paper-trade yet.
5. Category B/E/F/G items are real but secondary: none of them block anything if there's no edge to trade. Prioritize `manager.py` stop-loss retry, `position_sizer_v2.py` margin check, and the regime-filter non-wiring before going live once an edge exists — these affect capital safety, not discovery.

**On "maximize profit":** there is no honest answer to this yet. The system has not demonstrated it can make money after real costs on any instrument. Optimizing sizing/execution/profit before that is optimizing noise.
