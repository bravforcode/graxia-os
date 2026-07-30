# Bypass-loader classification — 2026-07-30

Classifies the 33 files in `scripts/check_bypass_loaders.py`'s `BASELINE` (scripts
defining their own OHLCV loader with no `BacktestEngine`/`provenance.py` import).
Produced by reading each file's actual verdict/cost logic, not by filename.

**Confirmed via repo-wide grep: none of these 33 files write directly into
`research/hypothesis_registry.json` or any `trial_ledger*.json`.** Registry/ledger
writes are confined to a separate, smaller set of files not in this list. So no
silent registry contamination exists among these 33 — but several of them produce
verdict-shaped output (Sharpe, DK-t, PBO, gate pass/fail) that could plausibly have
fed a human's manual decision to register a result, which is a real channel these
33 files were never checked against before.

## Most urgent finding

`scripts/validate_ram_strategy.py` (trial #1029's own validator) contains
`# Assume 0.1% daily cost baseline` — the identical fabrication pattern that
invalidated trial #1030. `strategies/regime_adaptive_multi_asset.py`'s
`compute_ram_metrics()` has **no cost/spread/slippage handling at all** — trial
1029's headline dk_t/Sharpe numbers were computed cost-free; the "cost stress
test" is a separate hand-derived approximation layered on top, not sourced from
`provenance.py` or measured spreads. Already reflected in trial 1029's
`invalidation_note` in `research/hypothesis_registry.json` (added 2026-07-30) —
does not change the verdict (trial already failed its own gates), but the scope
breach was never the only invalidity issue.

## CRITICAL / HIGH RISK — hardcoded or absent cost model, produces a verdict

| File | Issue |
|---|---|
| `validate_ram_strategy.py` | `# Assume 0.1% daily cost baseline` — fabrication pattern (see above) |
| `run_rydc_validation.py` | PnL computed as raw `(price-entry)/entry` — **no cost term anywhere in the file** |
| `test_ram_strategy.py` | Same underlying `compute_ram_metrics()` with zero cost handling |
| `tsm_backtest.py`, `tsm_ema.py`, `tsm_portfolio.py`, `tsm_validate.py` | Module-level `COST_BPS = 5` hardcoded, no source/justification comment |
| `comprehensive_edge_search.py`, `full_pipeline.py`, `research_backed_pipeline.py` | `cost_bps=10` hardcoded default throughout |
| `run_new_strategies_wf.py` | `cost_bps` default 10/15, hardcoded, no link to calibration file |

## MEDIUM RISK — reads a stale/copied cost snapshot rather than the live file

| File | Issue |
|---|---|
| `run_complete_analysis.py` | Hardcoded `SYMBOLS` dict of spread/slippage constants, looks real but is a static copy, not live-loaded |
| `run_multi_symbol_wf.py` | Hardcoded `COSTS` dict labeled "from config/cost_calibration.json" but not read from the file at runtime |
| `run_walk_forward.py` | **Worse than "falls back if not supplied" — the override path is dead code even when supplied.** See detailed finding below; do not remove from BASELINE until fixed. |
| `factor_control_check.py` | Consumes pre-computed return CSVs; risk is inherited from whatever produced them, not this file itself |

## LOWER RISK — doing it right (cite as the pattern to replicate)

| File | Why |
|---|---|
| `tsm_backtest_real_costs.py` | Per-asset measured spreads from `config/cost_calibration.json` |
| `run_multi_instrument_wf.py` | Documented use of measured Pepperstone costs from the calibration file |
| `select_tradeable_instruments.py` | Reads real `round_trip_bps_measured`; writes `config/selected_instruments.json`, which directly gates what `run_paper_trading.py` will trade — high leverage, low risk *if kept this way* |
| `tsm_paper_trade.py` | Live-execution bot (not a research verdict script); already uses per-asset measured costs, but should still be checked against `require_cost_calibrated()` since it's the actual live-money endpoint |

## DIAGNOSTIC / INFRA — no accept/reject verdict, lower priority

`audit_lookahead_v3.py`, `build_features_v3_multi_asset.py`, `cross_validate.py`,
`diagnose_features.py`, `diagnose_regime_accuracy.py`, `regime_filter.py`,
`research_approaches.py` (computes Sharpe with **zero** cost subtraction, but is
explicitly exploratory — flag if ever promoted), `research_dashboard.py`,
`retrain_calibrated.py`, `train_live_model.py`, `train_mega_model.py`,
`train_mega_model_v2.py`, `split_direction_c_holdout.py`, `stress_test.py`
(robustness check downstream of an already-decided model, not the verdict itself).

## Recommended order of work

1. `validate_ram_strategy.py` / `test_ram_strategy.py` — same fabrication class already caught twice; fix even though trial 1029 is already invalidated, since the file will be reused.
2. `run_rydc_validation.py` — worse than hardcoded, cost is entirely absent.
3. The four `tsm_*.py` files sharing `COST_BPS = 5` — one fix (route through `provenance.require_cost_calibrated` + real per-asset spread) fixes all four if factored into a shared helper.
4. `run_new_strategies_wf.py`, `comprehensive_edge_search.py`, `full_pipeline.py`, `research_backed_pipeline.py` — wire `cost_bps` to `config/cost_calibration.json` instead of a hardcoded default.
5. MEDIUM RISK group — replace copied constants with a live read of the calibration file so they can't drift.

Once a file is fixed to import a chokepoint, remove it from `BASELINE` in
`scripts/check_bypass_loaders.py` so the ratchet tightens.

## 2026-07-30 final status: all items 1-5 above closed, ratchet 32 → 20

Every item in the recommended order of work above is now resolved:

- Items 1-4 (CRITICAL/HIGH RISK, 8 files): fixed and removed from `BASELINE`.
  See the "HIGH RISK group fixed" section below.
- Item 5 (MEDIUM RISK, 4 files): `run_complete_analysis.py` and
  `run_multi_symbol_wf.py` fixed and removed from `BASELINE` (same
  live-gate-and-read pattern as the HIGH RISK group). `factor_control_check.py`
  has no cost logic at all and stays in `BASELINE` as a permanent, reasoned
  exemption. `run_walk_forward.py` is fixed at its actual root cause (a
  broken `--cost-config` pass-through one layer down, in `walk_forward.py`
  and `backtest_cost.py`) and also stays in `BASELINE` as a permanent
  exemption, since the file itself never makes a cost decision — see
  Finding 2/3 below and the `BASELINE` comment for the verification detail.

Remaining `BASELINE` entries (20) are the DIAGNOSTIC/INFRA and LOWER RISK
groups above plus these two permanent exemptions — none produce a
verdict-shaped result off a fabricated or silently-wrong cost.

## 2026-07-30 update: HIGH RISK group fixed, two new findings surfaced

All 7 CRITICAL/HIGH RISK files above (`validate_ram_strategy.py`,
`test_ram_strategy.py`, the four `tsm_*.py` files, `run_rydc_validation.py`,
`comprehensive_edge_search.py`, `full_pipeline.py`,
`research_backed_pipeline.py`, `run_new_strategies_wf.py`) are fixed, gated,
and removed from `BASELINE`. See `scripts/check_bypass_loaders.py`'s BASELINE
comments for the per-file verification notes (live re-run, verdict
unchanged, 81/81 regression suite green).

### Finding 1 (self-caught, fixed): `get_spread_bps()` is one-way, not round-trip

While wiring the fix above, all 5 of the `cost_bps=10` files were switched to
`paper_engine.campaign.get_spread_bps(symbol)`. That function returns
`spread_bps_measured` — the **one-way** spread — but every one of these
files applies its cost term exactly once per closed round-trip trade
(`pnl -= cost_bps / 10000` at exit). Using the one-way value there
understates real cost:

- XAUUSD: 0.3236 (one-way) vs 0.65 (`round_trip_bps_measured`) — 2x understated.
- USDJPY: 0.1236 (one-way) vs 7.25 (round-trip) — **~59x understated**, because
  USDJPY carries a real 7bps commission that the one-way spread field doesn't
  include at all.

Fixed by adding `paper_engine.campaign.get_round_trip_cost_bps(symbol)`
(reads `round_trip_bps_measured`, which already folds in commission where
measured) and repointing all 5 files at it. Re-verified live after the
correction: no verdict flipped (`research_backed_pipeline.py`'s
`momentum_12m` stayed `PASS_TO_NEXT_PHASE` 7/7, `full_pipeline.py`'s
`momentum_12m_xauusd` stayed `CONDITIONAL_PASS`, `run_rydc_validation.py`
stayed `FAIL` on all 5 gates) — XAUUSD's real round-trip cost is small
enough (0.65bps) that doubling it from the one-way figure didn't matter for
strategies with multi-bps edges. USDJPY results in
`comprehensive_edge_search.py --prong new_search` did move (one combo lost
its PROMISING tag) — expected, since that symbol's real cost is dominated by
commission the one-way field never carried. 81/81 regression suite still
green.

### Finding 2 (NOT fixed, do not remove from BASELINE): `run_walk_forward.py`'s `--cost-config` override is dead code

`run_walk_forward.py --symbol EURUSD --timeframe M15` (the documented
default invocation) looks calibrated — it defaults `--cost-config` to
`config/cost_calibration.json` and forwards it to two subprocess scripts.
Neither actually uses it:

1. **`scripts/walk_forward.py` line 404**: `if args.symbol in config:` checks
   the JSON's *top-level* keys (`version`, `date`, `source`, `assets`, ...),
   never `config["assets"][symbol]` where the real per-symbol data lives.
   This condition is never true for any real symbol, so the calibrated-cost
   branch (which also reads nonexistent fields `spread_cost_recommended` /
   `slippage_p90_recommended` — the actual schema has
   `spread_bps_measured` / `round_trip_bps_measured`, in bps not dollars)
   never fires. Confirmed no historical schema ever matched: both
   `config/cost_calibration.json` and `config/cost_calibration_live.json`
   have always used the nested `assets` structure with bps field names —
   this is not a migration break, the override path has never worked.
2. **`scripts/backtest_cost.py`** doesn't accept a `--cost-config` argument
   at all. `run_walk_forward.py`'s Phase 5 (`run_cost_backtest`) passes
   `--cost-config <path>` anyway; `argparse` (strict `parse_args()`) rejects
   it with `error: unrecognized arguments: --cost-config ...`, confirmed by
   direct invocation. `run_cost_backtest()` catches the nonzero exit and
   prints `[WARN] Cost backtest exited 2`, so Phase 5 silently produces no
   backtest result on every run.

Net effect: every `run_walk_forward.py` invocation — including the
documented `--symbol EURUSD` default, which isn't even in
`COST_CALIBRATED_SYMBOLS` — runs entirely on the flat CLI defaults
(`--spread-cost 0.024 --slippage-p90 0.02`, dollar amounts, no per-symbol
link) despite printing a header (`Cost: $0.044/trade`) that never claims
calibration and a `[Calibrated cost] ...` line that never prints. This is
the least dangerous form of the bug — it fails honestly by never claiming
success — but it means the "MEDIUM RISK" label undersold it: nothing here
is calibrated at all, ever.

**Fixed 2026-07-30**, matching the skip-not-guess pattern used elsewhere in
this file: `scripts/walk_forward.py` now imports
`provenance.require_cost_calibrated`, reads `config["assets"][symbol]` with
the real `round_trip_bps_measured`/`spread_bps_measured` fields, and raises
`UncalibratedCostError` instead of silently keeping the flat default when
`--cost-config` is passed for an uncalibrated symbol. The header print was
also reordered so `Cost: $...` reflects the resolved (real or flat) value
instead of always printing the pre-override flat default. Verified live:
`--symbol EURUSD --cost-config config/cost_calibration.json` raises
`UncalibratedCostError`; `--symbol XAUUSD` prints
`[Calibrated cost] XAUUSD: round_trip=0.000065 (real, spread-only -- no
measured slippage)` and proceeds. A pre-existing, unrelated `t0` NameError in
`run_walk_forward.py`'s `load_ohlcv_from_parquet` (referenced a variable that
only exists in the caller's scope) was also fixed — it crashed Phase 1 for
any symbol with real parquet data, before the cost-config fix could even be
exercised end-to-end.

Deliberately **NOT** fixed inline via a bps→dollar conversion, per the
original caution above — that needs position/contract semantics
(`backtest_cost.py`'s `cost_per_trade = (spread_cost + slippage_p90) *
price_arr * lot_mult`) that haven't been traced. Instead `backtest_cost.py`
got the matching, narrower fix: it previously didn't even accept
`--cost-config` (confirmed via direct invocation:
`error: unrecognized arguments: --cost-config ...`), so
`run_walk_forward.py`'s Phase 5 always failed silently on every run,
regardless of symbol. Added the flag with the same
`require_cost_calibrated` + real-schema-read + raise-loudly behavior for the
spread term only.

### Finding 3 (NOT fixed, documented): `backtest_cost.py` loads real
measured slippage and then never uses it

Separately from the `--cost-config` bug, `backtest_cost.py` already has a
**real, measured** slippage source: `load_slippage_p90()` reads
`artifacts/fill_samples_fixed/fill_samples_{symbol}_{freq}.csv` (an actual
fill simulator) and computes a P90 slippage-in-points figure. It's loaded
and printed (`Slippage P90 overall: N points ($X.XX)`) — and then never
referenced again. The actual cost computation
(`compute_trade_pnl`/`evaluate_backtest`) uses `args.slippage_p90`, the flat
CLI default (`0.000027`, return-units fraction), unconditionally. So every
run prints a real measured slippage figure to the console that has zero
effect on the reported P&L.

Not fixed here because the two values are in incompatible units — the fill
simulator's `slip['overall']` is in **points** (`POINT_VALUE = 0.01` dollars
per point, for 0.01-lot XAUUSD), while `args.slippage_p90` is a **return-unit
fraction** (dimensionless, price-relative). Converting one to the other
correctly requires knowing the point-value/lot/contract convention at the
moment of each trade — exactly the "position/contract semantics that haven't
been traced" boundary flagged for the spread-cost fix above, and worth its
own dedicated pass rather than a guessed conversion factor bolted onto
today's fix.
