# Lookahead Guard — Mechanism and Reachability Audit

**Trigger:** `test_backtest_guard_prevents_cheating_strategy` (`tests/test_lookahead_regression.py`) fails — expects 0 trades from a deliberately cheating strategy, gets 6. Confirmed pre-existing via stash-and-rerun.

## 1. Root cause

`core/lookahead_guard.py`'s `LookaheadGuard` has two independent mechanisms:

1. **Prevention by construction** — `get_slice()`, called every bar in `backtest/engine.py:591` (`bar_data = guard.get_slice(self.ohlcv_data)`) before `strategy.generate_signal()`. This is wired correctly and does truncate the `ohlcv_data`/`indicators` **arguments** passed to the strategy.
2. **Detection** — `check_data_access()`. Grepped the whole repo: **called only from tests, never from production code.** It is dead — decorative, not enforced.

The failure is that mechanism (1) only controls the *official* data channel (the function arguments). It has no way to stop a strategy that independently holds a reference to the full dataset, obtained before the engine sliced anything — e.g. a module-level class variable, a cache, or a direct read of a data file. `CheatingStrategy` in the regression test does exactly this: it stashes the full 200-bar array in `CheatingStrategy._full_data_ref` before `engine.run()` starts, then computes `future_idx = current_idx + 5` and checks it against `len(full_close)` (200) — the full array's length, not the length of the correctly-sliced `bar_data` it was handed. That check is true for ~195 of 199 bars, so a look-ahead signal is eligible almost every bar; the subset that also crosses the 0.1% price-change threshold and clears `max_positions`/SL filters becomes a real trade — reproducing the reported 6 trades against an expected 0.

**This is structural, not a one-line bug.** `get_slice()` cannot be patched to close this — Python has no way to stop a class from reading its own previously-stored reference. Closing it requires either (a) making `check_data_access()` mandatory somewhere strategies can't skip it, or (b) an audit/lint rule forbidding strategies from holding instance/module state that isn't derived from the per-call arguments.

## 2. Reachability — which trial harnesses actually go through this guard

Checked every `scripts/run_*.py` (25 files) plus the cross-sectional/crypto strategy modules for `BacktestEngine` usage (the only place `LookaheadGuard` is wired in — it does not exist anywhere else in the codebase).

**Guard-protected (uses `BacktestEngine`, therefore exposed to the bug above):**
- The single-asset bar-loop strategy family: `mlb`, `mrb`, `mtm`, `momentum_12m`, `donchian` (+ `_adx`/`_p1`/`_rsi`), `rsi_mean_reversion`, `bollinger_squeeze`, `volume_breakout`, `hybrid_mom_mr`, `dxy_divergence`, `rydc`, `mlmr`, `liquidity_sweep` (+`_v2`) — 17 files spot-checked for module/instance-level state that could replicate the `CheatingStrategy` bypass (global caches, file reads, stored full-array refs inside `generate_signal`). **No matches found.** This is a spot-check, not a line-by-line proof of absence — treat as weak-positive, not clearance.
- `scripts/run_ws_a.py` — the original WS-A momentum harness: imports and instantiates `BacktestEngine` for real (line 177), not just in a comment.

**NOT guard-protected (hand-rolled vectorized pandas, `LookaheadGuard` never imported — the guard bug is moot for these because there is no guard at all):**
- `scripts/run_ws_a_tsmom.py` — **the actual harness for trial 1028** (WS-A TSMOM, the one that tripped the cap). Its own docstring states: *"This harness does NOT use BacktestEngine (incompatible: SL-mandate, 50-bar..."*. Correctness here rests entirely on manual `.shift(1)`/`.shift(LOOKBACK)` discipline in the script, unaudited by any guard mechanism.
- `scripts/run_ws_a_trial_1028.py` — mentions `BacktestEngine` only as a data-shape smoke-test (`BacktestEngine().load_data(data, timestamps)` inside a try/except, to confirm the provenance-loaded frame maps correctly) — **not** the engine that produced trial 1028's reported statistics. The real computation is in `run_ws_a_tsmom.py` above.
- `scripts/funding_rate_arb_rigor.py`, `scripts/funding_rate_arb_pilot.py`, `scripts/crypto_basis_carry_rigor.py` — zero `BacktestEngine` references.
- `strategies/khubiev_portfolio.py` (cross-sectional / "TSM Portfolio" family) and its test `tests/test_khubiev_portfolio.py` — zero `BacktestEngine` references.
- The remaining 21 `scripts/run_*.py` files (walk-forward, validation, release-gate, PBO, deflated-Sharpe, dry-run scripts) — no `BacktestEngine` reference either; these appear to be orchestration/validation wrappers around results rather than raw backtests, but were not individually categorized further here.

## 3. What this means for historical verdicts

- **Single-asset trials (the 33+ family) and the original WS-A momentum run**: these did go through the guard-protected path. The guard's *prevention* mechanism (get_slice) is real and correctly wired for the argument-passing channel; the spot-check found no obvious side-channel in the strategy files themselves. Confidence: moderate, not proof — a full line-by-line read of all 17 strategy files (plus any shared feature/indicator modules they call) is the remaining gap before calling this family fully cleared.
- **Cross-sectional momentum (TSM Portfolio), funding-rate arb, crypto basis/carry, and WS-A TSMOM (trial 1028)**: the guard bug is **irrelevant** to these — they were never inside its scope. Their correctness depends entirely on each script's own manual lag/shift discipline, which has not been audited here and needs its own line-by-line pass per script (checking every `.shift()`, `.rolling()`, and cross-sectional ranking operation for same-bar or future leakage). This is a larger, separate body of work than the guard fix itself, and arguably the more consequential gap: it means the REJECTED verdicts for these families were never guard-verified in the first place, guard-bug or no guard-bug.

## 4. Fix applied (2026-07-30)

`BacktestEngine.run()` now calls `_reset_strategy_class_state()` before the main loop: any non-empty `list`/`dict`/`tuple`/`set` held at the strategy **class** level (not instance — `__init__` state is untouched) is reset to empty before every run. This closes the `CheatingStrategy._full_data_ref` vector specifically, and closes the general class of bug it represents (a class-level mutable cache surviving across runs/instances — a real Python footgun independent of adversarial intent). It does **not** and cannot close a strategy that re-reads external state fresh inside `generate_signal()` on every call (e.g. hitting a file or a live cache each bar) — that remains architecturally unblockable in-process; a real strategy doing this would need a code-review-level check, not a runtime guard.

Verified: `tests/test_lookahead_regression.py` — all 7 tests pass, including `test_backtest_guard_prevents_cheating_strategy` (previously 6 trades, now 0).

This raises confidence on the single-asset family (§3) from "moderate" to "verified for this specific vector" — the guard now actively defends against it rather than being silently absent. The hand-rolled-harness gap (§2, §3) is unaffected by this fix and remains open.

## 6. Hand-rolled harness lag/lookahead audit (2026-07-30)

Line-by-line read of all 5 unaudited hand-rolled harnesses from §5 item 2 (now completed). Two real findings, three clean.

### 6.1 `scripts/run_ws_a_tsmom.py` (trial 1028 — the actual trial that tripped the cap) — **methodology inconsistency, not classic future-leakage**

`compute_signal()` (line 96) computes `ret_12m = close / close.shift(LOOKBACK) - 1` and `realized_vol` via a rolling window ending at the current bar — both are contemporaneous (use data through bar `i`, never bar `i+1` or later). This is NOT future-data leakage.

However, `run_backtest()` — the function that actually produces the headline Sharpe, trade count, and P&L (lines 119–285) — enters and exits positions at `df["close"].iloc[idx]` (lines 202, 224) using the signal computed **from that same bar's close** (line 191: `signals[sym].iloc[idx]`). Signal-decision and fill happen on the identical bar/price with zero lag — an optimistic same-print execution assumption.

Separately, the statistical-validation pipeline in `main()` (line 421: `signal_ret = sig.shift(1) * ret`) properly lags the signal by one bar before computing the DK-test/jackknife input series.

**Net effect:** the reported Sharpe (`m["sharpe"]`) and trade count come from the zero-lag engine; the DK t-stat and DSR skew/kurtosis inputs come from the lag-1 engine. Two different implied trading systems feed one "primary gate" verdict. For trial 1028 specifically this doesn't overturn the REJECT — the gate that actually failed (`dk_t=0.428 < 2.0`) is computed on the *more conservative*, correctly-lagged series, so the rejection is if anything under-generous to the strategy, not falsely lenient. But the Sharpe/trade-count numbers quoted alongside that verdict (in the trial ledger, in this document's §2 table) are from the optimistic zero-lag engine and should not be read as the lag-realistic figures. Not a guard-bypass (no `BacktestEngine` involved, so §4's fix doesn't touch this), and not the `CheatingStrategy`-style class-state vector — a distinct, harness-specific same-bar-fill assumption baked into the P&L loop itself.

### 6.2 `strategies/khubiev_portfolio.py` — **real in-sample leakage, currently inert (no registered trial uses it)**

`KhubievPortfolio.__init__` defaults to `fit_on_init=True, train_fraction=1.0` (lines 160–161). `fit()` (line 242) trains the forecasting model's weights on the **entire** historical return series in one shot, via gradient descent that directly optimizes a Sharpe/drawdown-style loss over that whole window (lines 304–331). `generate_signal()` (line 486) then scores every bar using those same fixed, full-history-trained weights (`_asset_score`, line 458) — there is no walk-forward split, no online refit, nothing gating the model from having "seen" returns that occur after the bar being scored.

If this strategy were ever run through a backtest over the same historical window it was fit on (the default behavior, since `train_fraction=1.0`), every historical signal would be generated by a model that already knows the entire future return path via its trained weights — a severe leakage, categorically worse than the same-bar issue in §6.1 because it's whole-dataset, not single-bar.

**Scope check:** grepped `research/trial_ledger.json` and both `reports/edge_search_2026/` and `reports/paper_engine/` — `khubiev` does not appear in any trial record. `tests/test_khubiev_portfolio.py` always passes `fit_on_init=False` (line 55), so the test suite never exercises the leaking default path either. This strategy is real, implemented-per-paper code (`arXiv 2509.04541`) that has apparently never been run through a formal trial — so no existing REJECT/ACCEPT verdict is contaminated by it. It is, however, a live landmine: the very next person who instantiates `KhubievPortfolio()` with default args and backtests it over historical data will get a fully in-sample-leaked result and could mistake it for a real edge. Needs either a hard `train_fraction < 1.0` default, a walk-forward refit loop, or a runtime guard that refuses to `fit()` on data extending past the bar currently being scored — before this strategy is ever used for a real trial.

### 6.3 `scripts/funding_rate_arb_rigor.py`, `scripts/funding_rate_arb_pilot.py`, `scripts/crypto_basis_carry_rigor.py` — clean, lookahead concept doesn't apply

All three measure **realized historical cashflows** (funding payments actually paid historically, or futures-basis convergence actually observed) rather than running a signal-timing strategy that makes a forward decision from historical data. There is no entry/exit timing choice that could consult future information — the computation is "sum what already happened," assuming continuous holding. `crypto_basis_carry_rigor.py` in particular is unusually careful methodologically: it explicitly computes and labels a naive level-based NW test as "COMPARISON ONLY, DO NOT DECIDE ON" (line 150) because it correctly identifies that series as spuriously near-unit-root, and uses the stationary returns-based series as the actual decision input (line 119, `returns_based_nw_significance_PRIMARY`). No changes needed.

## 8. Full read of the 17 single-asset strategy files (2026-07-30)

Read every one of the 17 files named in §2 in full, not spot-checked. Checked for the two vectors already proven to matter in this repo: (a) class/module-level mutable state surviving across runs or bars (the `CheatingStrategy` vector, closed at the engine level by §4 but worth confirming no strategy relies on it), and (b) a model or coefficient set fit on data that includes bars after the one being scored (the `KhubievPortfolio` vector, §6.2).

**16 of 17 clean**, several with explicit prior lookahead-safety work visible in the code:
- `mlb.py` — `_compute_swing_labels()` carries a comment explaining a centered-rolling-window lookahead was found and fixed by shifting the label forward `window // 2` bars.
- `rydc.py` — `RollingOLS.update()` is commented "No look-ahead: coefficients estimated on data through t-1 only" and the slicing (`[-(window+1):-1]`) actually does this correctly.
- `liquidity_sweep.py` / `liquidity_sweep_v2.py` — both carry "P1-2/P1-3 FIX: exclude current bar from lookback window" comments, and the slicing (`[-(lookback+1):-1]`) correctly excludes the current bar.
- `donchian.py`, `donchian_adx.py`, `donchian_rsi.py`, `bollinger_squeeze.py`, `mlmr.py` (technical side), `mtm.py`, `rsi_mean_reversion.py`, `hybrid_mom_mr.py`, `dxy_divergence.py`, `mrb.py`, `volume_breakout.py`, `momentum_12m.py` — all derive every quantity from `ohlcv_data`/`indicators` arguments only, using only already-elapsed bars (`[-N:]`/`[-N-1:-1]` slicing patterns), no class-level containers, no external data reads inside `generate_signal`.
- `donchian_p1.py` — carries genuine cross-bar instance state (`self._raw_pos`, `self._eff_pos`, needed to track an already-open position for a flip-until-reversal strategy), with an explicit comment stating the safety precondition ("one fresh instance per single, strictly-sequential `BacktestEngine.run()` pass"). Instance state, not class state — outside the vector closed in §4, and correctly scoped for what it needs to do.

**1 of 17 — `mlmr.py` — same leak category as `KhubievPortfolio`, but the leak (if any) lives outside this file.** `_load_model()` (line 166) globs `core/ml/models/xgboost_{symbol}*.pkl`, takes the lexicographically-last match, and caches it (`self._model_loaded = True`) for reuse across every bar of a run. This file's own code never touches the training process — but if the on-disk `.pkl` it loads was trained on the strategy's *entire* historical window (rather than point-in-time / walk-forward), then every historical signal MLMR ever generated in a backtest was scored by a model that had already seen data from after that bar, structurally identical to §6.2. `Grep` found an extensive ML-training surface in this repo (`scripts/train_live_model.py`, `scripts/train_mega_model.py`, `scripts/train_all_models.py`, `validation/walk_forward.py`, `ml/models/manifest.json`) — enough infrastructure that walk-forward-correct training is plausible, but confirming which script actually produced whichever `.pkl` MLMR would load, and whether that script used walk-forward or full-history fitting, is a separate, non-trivial investigation not completed here. **Do not treat MLMR's historical results (if any exist) as clean until that's checked.**

Net effect: confidence on the single-asset family (§3) upgraded from "moderate, spot-check only" to "verified for the class-state and OLS/window-slicing vectors, with one flagged open question (MLMR model-training provenance)."

### 8.1 MLMR provenance — resolved (2026-07-30): not a leak, but a different, real bug

Traced it. `mlmr.py:172` does `from ..core.safe_pickle import safe_load_ml_model` — **this function does not exist anywhere in the codebase.** `core/safe_pickle.py` only defines `safe_load_model` (confirmed by reproducing the exact `ImportError: cannot import name 'safe_load_ml_model' ... Did you mean: 'safe_load_model'`, and by `git log --all --branches --remotes -S "safe_load_ml_model"` returning zero commits across all history — same forensic check used earlier this session for `DynamicKellySizer`, same result: never existed, on any branch, ever).

`_load_model()`'s call to this nonexistent function is wrapped in a broad `except Exception` (line 204) that logs `mlmr.model_load_error` and returns `False`. The caller (line 247) only logs a debug line on failure and continues — it does **not** abort the signal. Net effect: `self._model` stays `None` forever, the `if self._model is not None:` guard (line 299) is never true, and every MLMR signal ever generated with default construction used the hardcoded `ml_prob = 0.65` fallback (line 298) as its confidence — not a real model prediction — while the strategy's docstring and log messages describe it as ML-confirmed.

This **resolves §8's open question in the safe direction**: MLMR cannot currently load *any* model, walk-forward-trained or otherwise, so the full-history-leak scenario feared in §8 cannot occur — the failure mode is "silently degrades to constant-confidence technicals," not "silently leaks the future." No historical MLMR result is lookahead-contaminated by this path, because no model was ever actually loaded to begin with.

It also isn't simply a typo to patch. `core/safe_pickle.py`'s `safe_load_model()` (the real function) rejects xgboost classes via `RestrictedUnpickler` unless either (a) a valid HMAC signature sidecar (`<path>.sig`) is present and `signing_key` is passed — none of the `.pkl` files in `ml/models/` have a `.sig` file — or (b) `allow_unsigned=True`, which the function's own docstring flags: *"RESEARCH/DEV ONLY... MUST be False in production entry points... model-substitution risk."* So making MLMR's ML path actually work means either standing up model signing for these artifacts, or deliberately accepting the unsigned-research-mode risk — a security tradeoff, not a one-line fix, and not mine to decide unilaterally. Filed as open, not patched.

Separately, worth a skeptical glance whenever `ml/models/manifest.json` is next touched: its XAUUSD entry reports `z_score: 31.8` and `edge_status: "EDGE_CANDIDATE"` alongside a confusion matrix of `[[0, 68115], [0, 80305]]` — that's a classifier predicting the same class 100% of the time (zero entries in the "predicted 0" column for either true class), which is degenerate, not evidence of edge. Not re-litigated here since it's outside MLMR's actual code path (MLMR can't load this model anyway, per above) and outside the now-closed research thread — flagged only so it isn't mistaken for a clean result if anyone revisits `ml/models/` later.

## 9. Recommended next steps

1. Fix the guard architecture (make `check_data_access` load-bearing, or add a strategy-authoring lint rule against externally-held state) — closes the `CheatingStrategy` class of bug for the `BacktestEngine` path. [DONE 2026-07-30, see §4]
2. ~~Line-by-line lag audit of the 5 hand-rolled harnesses~~ — [DONE 2026-07-30, see §6]. Two follow-ups from that audit remain open:
   - Decide whether trial 1028's reported Sharpe/trade-count in the ledger need a footnote or re-run against the lag-1 engine (§6.1) — the REJECT verdict itself doesn't change, but the quoted headline numbers are optimistic.
   - Fix `KhubievPortfolio`'s leaking default (`train_fraction=1.0`, `fit_on_init=True`) before it is ever used in a real trial (§6.2) — currently inert/unused, so no urgency to re-run anything, but it should not ship as-is.
3. ~~Full (non-spot-check) read of the 17 single-asset strategy files~~ — [DONE 2026-07-30, see §8]. One new open item from that pass: trace which training script produced any `.pkl` model `mlmr.py` would load, and confirm walk-forward (not full-history) fitting, before trusting any historical MLMR result.
