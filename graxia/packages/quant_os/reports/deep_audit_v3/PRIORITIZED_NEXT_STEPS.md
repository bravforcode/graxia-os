# PHASE 27 — PRIORITIZED NEXT STEPS
*P0 = blocks paper trading · P1 = before paper trading · P2 = before real money · P3 = quality.*

---

## P0 — Hard Blockers (resolve before ANY further paper/live trading)

### P0-1: Run the label-shuffle null test (cheapest possible edge verdict)
- **Triggered by**: Phase 13.1
- **Current state**: `tests/test_label_shuffling.py` exists, correctly implemented, but has **never been run**; no result artifact.
- **Required state**: execute against current best config, record `real_sharpe`, `null_95th_percentile`, `p_value`, `survives` to `reports/`.
- **Concrete action**: `cd graxia/packages/quant_os && python -m pytest tests/test_label_shuffling.py -s` (or call `run_label_shuffle_test(features, labels, n_permutations=100)` directly); save JSON to `reports/label_shuffle_result.json`.
- **Falsification**: `survives=True` with `p_value < 0.05` and `real_sharpe > null_95th`. If `survives=False`, the edge thesis is dead — STOP.
- **Complexity**: Low (test already written). **~10 minutes.**

### P0-2: Fix cost-model unit bugs
- **Triggered by**: Phase 3.2 (hand re-derived, confirmed).
- **Current state**: `execution/cost_model.py:43` `slippage_cost = spread_points × …` (slippage≡spread); `backtest/engine.py:726` `0.01 × spread_pips` is 100× wrong for 5-digit FX majors.
- **Required state**: slippage modeled independently (size-vs-liquidity, or at least a separate configurable slippage_points input); pip→price conversion keyed to symbol digits (`0.0001` for 5-digit FX, `0.01` for JPY/XAUUSD).
- **Concrete action**: in `backtest/engine.py:726`, replace `Decimal("0.01") * spread_pips` with a symbol-aware pip size from `InlineContractSpec.trade_tick_size` × 10 (or a `pip_size` field); in `cost_model.py:43`, take `slippage_points` as a separate parameter, not reuse `spread_points`.
- **Falsification**: hand-re-derive a EURUSD trade's spread cost and confirm code matches within rounding; `tests/test_cost_unit_regression.py` passes for FX majors.
- **Complexity**: Medium (touches sizing + cost path; needs regression tests for each symbol class).

### P0-3: Establish backtest/live parity (single shared feature+strategy path)
- **Triggered by**: Phase 8.1 (three divergent code paths).
- **Current state**: backtest exercises `strategies/mtm,mrb,mlb`; live runs `regime/` stack; `scripts/backtest_suite.py` is a third uncosted path.
- **Required state**: ONE feature-computation function and ONE strategy implementation used by both `BacktestEngine` and `run_paper_trading.py`, with a `test_feature_parity.py` asserting numerical equality on identical input.
- **Concrete action**: decide which strategy is the candidate (the `regime/` liquidity-sweep is what live trades → backtest THAT, not MTM); refactor so `BacktestEngine` and `PaperTrader` import the same `generate_signal`.
- **Falsification**: `tests/test_feature_parity.py` asserts live-path output == backtest-path output for the same bars within float tolerance.
- **Complexity**: High (architectural; the two stacks were built separately).

### P0-4: Stop publishing `results/backtest_suite_*.json` as a backtest
- **Triggered by**: Phase 3.6 (R14).
- **Current state**: `scripts/backtest_suite.py` produces bar-return summaries mislabeled as trade metrics (`n_trades=59999`, `profit_factor=Infinity`).
- **Required state**: either delete the script or rename outputs to `bar_return_scan_*.json` and remove all `n_trades`/`win_rate`/`profit_factor` fields (they are meaningless for a continuously-rebalanced return series).
- **Concrete action**: edit `scripts/backtest_suite.py:94-102` `calc_metrics` to drop trade-metric labels, or add a header comment + rename.
- **Falsification**: no file in `results/` claims `n_trades` for a bar-return scan.
- **Complexity**: Low.

---

## P1 — Paper Trading Blockers

### P1-1: Independent feed cross-validation
- **Triggered by**: Phase 2.2. Run `scripts/download_duka.py` for the same 7-day XAUUSD window, diff close-to-close vs `data/XAUUSD_M1.csv`, save to `reports/feed_xval.md`. Complexity: Medium.

### P1-2: Verify the kill-switch order-path gate
- **Triggered by**: Phase 9.2. Confirm `run_paper_trading.py`'s order-submission path calls `kill_switch.is_active()` before every order. If absent, add it. Complexity: Low.

### P1-3: Resolve `max_open_positions` conflict
- **Triggered by**: Phase 0.4 #1, Phase 9.2. `core/config.py:66`=5 vs `risk_policy.py:14`=1. Pick one (likely 1, per `RiskPolicy`), delete the other or route config through `RiskPolicy`. Complexity: Low.

### P1-4: Close the Phase 1 leakage gaps
- **Triggered by**: Phase 1.4/1.6. Grep repo for `bfill`, `center=True`, `MinMaxScaler.fit`; read `ml/pipeline.py` scaler-fit location; confirm fit-on-train-only. Complexity: Low–Medium.

### P1-5: External watchdog for crash recovery
- **Triggered by**: Phase 9.2. The in-process DMS dies with the process. Add a systemd unit / PM2 / separate healthcheck process that restarts the bot (and respects kill-switch persistence). Complexity: Medium.

### P1-6: Wire reconciliation on startup + every loop
- **Triggered by**: Phase 9.5, 21.5. Confirm `execution/reconcile.py` is called on boot and per-loop; define the action on mismatch (alert+halt). Complexity: Medium.

### P1-7: Run the cost-stress matrix (0.5×–5×)
- **Triggered by**: Phase 13.3. Extend `cost_model.py:ALL_SCENARIOS` to include 5×, run on best config, report zero-crossing multiplier. Complexity: Low.

### P1-8: Collect ≥2 weeks of data (enables 5min/15min + tail-event-adjacent windows)
- **Triggered by**: Phase 0.5, 12. 7 days is too short for any meaningful OOS inference or regime coverage. Complexity: Low (time, not effort).

---

## P2 — Live Capital Blockers (selected; full list in Phase 25)

- P2-1: Compute DSR + PBO/CSCV (modules exist) — Phase 3.7, 6.7.
- P2-2: Capacity ceiling + slippage-curve run — Phase 10.3.
- P2-3: Kelly fraction derivation from confirmed win-rate/payoff — Phase 10.2.
- P2-4: Tail-event stress replay (synthetic shock until real tail data exists) — Phase 12.2.
- P2-5: Broker regulatory/counterparty confirmation (Pepperstone disclosures) — Phase 11.1.
- P2-6: Hardening — log rotation, disk/mem monitors, Sentry DSN — Phase 21.
- P2-7: Holiday/weekend-gap spread modeling — Phase 1.8.
- P2-8: MT5 Magic Number + broker TOS stop-out level check — Phase 9.4/9.7.

---

## P3 — Quality Improvement

- P3-1: Decompose 53 files ≥500 LOC (esp. `backtest/engine.py` 1090, `gold_bot/core/engine.py` 951) — Phase 18.1.
- P3-2: Delete or clearly fence off the `gold_bot/` second engine (Phase 18.2 — duplicated engine logic).
- P3-3: Repo-wide `np.random.seed` audit + data manifest content-hash lock (Phase 17.2/19).
- P3-4: Add `pandas_ta` to `requirements.txt` or remove the silent-fallback `except ImportError` at `engine.py:669` (Phase 0.2).
- P3-5: Pre-committed live sequential stopping rule (SPRT/CUSUM) — Phase 22.2.
- P3-6: Third-party runbook review — Phase 23.1.

---

## Re-evaluation of Known Planned Items

| Planned item | Audit verdict |
|---|---|
| Regime filtering via ATR-percentile | Phase 5 not run; but regime selection concentrates on low-vol bars where edge<cost (`SUMMARY.md:16`) — regime filtering may *amplify* the cost/move problem. Test before building more. |
| Multiple-testing correction | **Do first** — without trial count, every "significant" finding is suspect. |
| ForexFactory calendar integration | `events/`, `news_events/` infra exists; `[join logic untraced]`. Low priority until an edge is confirmed. |
| Capacity & Kelly sizing | Premature — no confirmed edge to size. Kelly on the current (negative) expectancy outputs **0**; sizing for a non-edge is a category error. |
| Broker/regulatory verification | Needed before live; not before paper. |
| Adversarial validation suite | **Highest leverage** — make `test_label_shuffling.py` a reusable, seeded, auto-run gate (P0-1). |

---

## The Single Most Important Next Action

**Run `tests/test_label_shuffling.py` today.** It is already written, costs ~10 minutes, and is the cheapest possible disambiguation between "we have an edge that survives costs once bugs are fixed" and "we have no edge and should STOP." Every other next step is downstream of that verdict. Not running it is the single most expensive form of procrastination available, because it preserves ambiguity that could be resolved in one command.
