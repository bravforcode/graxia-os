# PHASE 7 — BACKTEST / WALK-FORWARD INTEGRITY
*Per R1–R18. Cross-references Phase 3, 4.*

---

## 7.1 — Transaction Cost Model (Final Verification)

- Where costs are subtracted: **canonical engine** subtracts commission at entry (`engine.py:789` `self.balance -= result.commission`) and at exit (`engine.py:902-905`). Spread/slippage enter via `entry_spread_cost` / `entry_slippage_cost` / `exit_slippage_cost` on the `BacktestTrade` and P&L is computed from `exit_price - entry_price` (`engine.py:895-898`) — the spread/slippage is already baked into `entry_price`/`exit_price` via `simulate_entry`/`simulate_exit`. **So costs ARE applied per-trade in the canonical engine.** ✓
- **Per trade or per bar?** Per trade. ✓
- Swap/rollover: `BacktestConfig.enable_swap=True` (`engine.py:142`) and `execution/swap_model.py` exist — **but `engine.py`'s `_close_position` (lines 890-905) does NOT call any swap computation.** The `enable_swap` flag is read nowhere in the close path. **`[BUG: swap flag is dead; overnight positions incur no swap cost in backtest]`** → P1 (material if any position held overnight).
- Slippage model: present (half-spread, Phase 4.2) but slippage = spread (Phase 3.2 bug).
- **2× spread worst-case test**: `cost/` and `validation/cost_stress.py` + `STRESS_2` scenario (`cost_model.py:17`) exist → capability present. Whether the *current best config* survives 2× `[NOT RUN this session]`. → P1.

## 7.2 — Fold Construction

`walk_forward.py:113-160`:
- Requires `total_bars >= 1000` (`walk_forward.py:115-116`). **XAUUSD M1 = 5000 bars → passes minimum, but 7-day window means folds span hours not regimes.**
- OOS size = `total_bars // (n_windows+1)`; IS size derived from `is_ratio=0.7`. Folds defined by **row count** (`walk_forward.py:119-120`), not time period → "variable-time-length folds that may span different market regimes" (protocol concern) — but with only 7 days, all folds are the same regime anyway.
- **Gap between IS-end and OOS-start?** `walk_forward.py:138-139` rolling mode: `is_end_idx = oos_start_idx` — **NO gap**. Autocorrelation bleed risk (protocol 7.2). → P2.
- **Test set touched during search?** `[UNVERIFIED]` — depends on whether `optimize_func` was ever pointed at OOS; not enforceable from code alone.

## 7.3 — Order Execution Realism

- Canonical engine: signal at bar i → fill at bar i+1 open (`engine.py:772` `fill_time = timestamps[bar_index+1]`; `execution_simulator.py:183` `fill_idx = bar_index + 1`). **Next-bar-open execution — the realistic assumption.** ✓
- `scripts/backtest_suite.py`: `signal.shift(1) * returns` (`backtest_suite.py:25`) — signal at t-1 paired with return at t. **Effectively next-bar execution too, but with NO spread/slippage/commission deducted.** ✗ (Phase 3.6).

## 7.4 — Position Management in Backtest

- Max 1 position per symbol: `engine.py:689-691` rejects if `pos.symbol == signal.symbol` already open. ✓
- `max_positions` global cap: `engine.py:686-687`. ✓
- New signal while position open: **ignored** (returns early). ✓
- Backtest/live consistency: see Phase 8.

## 7.5 — Performance Degradation Analysis

`walk_forward.py:182-187` computes `is_oos_ratio = oos_pf / is_pf` per fold; `validate_walk_forward_requirements` (`walk_forward.py:240-258`) checks `avg_is_oos_ratio >= 0.5`. **Framework exists.** Actual per-fold numbers for the current best config `[NOT RUN this session]`. → P1.
- Parameter sensitivity ±20%: `core/param_sweep.py`, `validation/parameter_stability.py` exist — capability present, results `[NOT RUN]`.

## 7.6 — Final Verdict

> *"Is there currently a statistically significant, cost-adjusted, out-of-sample edge?"*

**INSUFFICIENT EVIDENCE — leaning NO.**

- OOS trades: the only costed run (`SUMMARY.md`) had **67 trades** — far below the 200-trade minimum (Phase 6.1). Net P&L was **negative (-$23.21)**.
- The `results/backtest_suite_*.json` "Sharpe 1.31" is from an uncosted bar-return script (Phase 3.6) — not evidence of edge.
- p-value / multiple-testing correction: `[NOT COMPUTED/REPORTED in any artifact found]`.
- No walk-forward OOS Sharpe with CI is reported anywhere.

**There is no statistically significant, cost-adjusted, out-of-sample edge in any artifact on disk.** The project's own `SUMMARY.md` says the strategy does not survive real costs.

## 7.7 — Tick vs Bar Reconciliation

`[NOT PERFORMED]` — `data/ticks/` empty. See Phase 4.3.

## 7.8 — Historical Cost-Schedule Changes

`backtest/dynamic_spread_model.py` uses **current** Pepperstone Razor session spreads uniformly across history. For a 7-day window this is immaterial; for multi-year history it would be. → P3 (moot until longer data exists).

---

## Phase 7 — Verdict

**STATUS: FAIL (no edge demonstrated) + 1 confirmed bug (dead swap flag).**

- Cost model: applied per-trade in canonical engine ✓, but slippage=spread bug (Phase 3.2) and swap flag dead (`engine.py:142` never read in close path) ✗.
- Walk-forward framework: present and structurally sound, but never run on data long enough to span a regime change.
- **No statistically significant OOS edge exists in any artifact.** `SUMMARY.md` itself reports a net loss after costs.
